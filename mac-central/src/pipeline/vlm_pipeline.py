"""VLM processing pipeline — extracted from CentralOrchestrator._vlm_worker."""

import asyncio
import time
from typing import Any, Optional

from src.core.logging import get_logger
from src.core.event_bus import EventBus
from src.observability.metrics import vlm_requests_total, vlm_latency, vlm_queue_depth
from src.observability.circuit_breaker import CircuitBreaker
from src.observability.tracing import span

logger = get_logger(__name__)


class VLMProcessingPipeline:
    """Background VLM inference: queue, batch accumulation, circuit breaker,
    RAG injection, conversation management, cloud upload, config guidance."""

    def __init__(
        self,
        vlm_queue: asyncio.Queue,
        inference_engine,
        event_bus: EventBus,
        circuit_breaker: Optional[CircuitBreaker] = None,
        alert_manager=None,
        cloud_storage=None,
        rag_retriever=None,
        vlm_config_guide=None,
        batch_max_size: int = 8,
        batch_timeout: float = 2.0,
    ) -> None:
        self._vlm_queue = vlm_queue
        self._inference_engine = inference_engine
        self._event_bus = event_bus
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._alert_manager = alert_manager
        self._cloud_storage = cloud_storage
        self._rag_retriever = rag_retriever
        self._vlm_config_guide = vlm_config_guide
        self._batch_max_size = batch_max_size
        self._batch_timeout = batch_timeout
        self._worker_task: Optional[asyncio.Task] = None
        self._command_queue: Optional[asyncio.Queue] = None
        self._command_id_counter = 0

    def set_command_queue(self, q: asyncio.Queue) -> None:
        self._command_queue = q

    def set_command_id_counter(self, counter: int) -> None:
        self._command_id_counter = counter

    @property
    def command_id_counter(self) -> int:
        return self._command_id_counter

    async def start(self) -> None:
        """Start the background VLM worker task."""
        self._worker_task = asyncio.create_task(self._worker())

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Drain queue and cancel worker."""
        if self._worker_task and not self._vlm_queue.empty():
            logger.info(f"Draining VLM queue ({self._vlm_queue.qsize()} items)...")
            try:
                await asyncio.wait_for(self._vlm_queue.join(), timeout=timeout)
                logger.info("VLM queue drained successfully")
            except asyncio.TimeoutError:
                remaining = self._vlm_queue.qsize()
                logger.warning(f"VLM drain timeout, {remaining} items discarded")

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """Background worker that processes VLM analysis requests in batches."""
        logger.info("VLM worker started (batch mode)")

        while True:
            batch = []
            try:
                item = await self._vlm_queue.get()
                batch.append(item)
                deadline = asyncio.get_event_loop().time() + self._batch_timeout
                while len(batch) < self._batch_max_size:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(
                            self._vlm_queue.get(), timeout=remaining
                        )
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break
            except asyncio.CancelledError:
                break

            vlm_queue_depth.set(self._vlm_queue.qsize())

            # Try batch inference first, fall back to sequential
            batch_results = None
            if hasattr(self._inference_engine, 'batch_analyze') and len(batch) > 1:
                try:
                    batch_items = [{"frame_data": it["frame_data"], "prompt": it["prompt"]}
                                   for it in batch]
                    t0 = time.perf_counter()
                    batch_results = await asyncio.wait_for(
                        self._inference_engine.batch_analyze(batch_items),
                        timeout=30.0 * len(batch),
                    )
                    elapsed = time.perf_counter() - t0
                    logger.info(f"Batch VLM: {len(batch)} items in {elapsed*1000:.0f}ms")
                except Exception as e:
                    logger.warning(f"Batch inference failed, falling back to sequential: {e}")
                    batch_results = None

            for idx, item in enumerate(batch):
                await self._process_item(item, idx, batch_results)

    async def _process_item(self, item: dict, idx: int, batch_results) -> None:
        """Process a single VLM queue item."""
        if not self._circuit_breaker.allow_request():
            vlm_requests_total.labels(status="circuit_open").inc()
            logger.warning("Circuit breaker open, skipping VLM request")
            self._vlm_queue.task_done()
            return

        try:
            t0 = time.perf_counter()
            device_id = item.get("device_id", "")
            prompt = item["prompt"]

            # RAG: inject historical context (v2)
            if self._rag_retriever and device_id:
                try:
                    class_names = [d.get("class_name") for d in item.get("detections", [])]
                    rag_ctx = self._rag_retriever.retrieve(device_id, class_names=class_names)
                    if rag_ctx.items:
                        rag_text = self._rag_retriever.format_for_prompt(rag_ctx)
                        prompt = f"{prompt}\n\nHistorical context:\n{rag_text}"
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")

            # Multi-turn: build prompt with conversation history
            if device_id and self._inference_engine:
                ctx = self._inference_engine.get_conversation(device_id)
                prompt = ctx.build_prompt(prompt)

            with span("vlm_inference", {
                "device_id": device_id,
                "frame_id": str(item["frame_id"]),
                "rule": item.get("rule", ""),
            }):
                if batch_results is not None and idx < len(batch_results):
                    vlm_result = batch_results[idx]
                else:
                    vlm_result = await asyncio.wait_for(
                        self._inference_engine.analyze_image(
                            item["frame_data"], prompt
                        ),
                        timeout=30.0,
                    )

            # Record conversation turn
            if device_id and self._inference_engine:
                ctx = self._inference_engine.get_conversation(device_id)
                ctx.add_turn("user", item["prompt"])
                ctx.add_turn("assistant", vlm_result[:200])

            elapsed = time.perf_counter() - t0
            vlm_latency.observe(elapsed)
            self._circuit_breaker.record_success()
            vlm_requests_total.labels(status="success").inc()
            logger.info(f"VLM result (frame {item['frame_id']}): {vlm_result[:100]}...")

            self._event_bus.publish({
                "type": "vlm_analysis",
                "frame_id": item["frame_id"],
                "trace_id": item["trace_id"],
                "device_id": device_id,
                "detections": item["detections"],
                "vlm_result": vlm_result[:200],
                "rule": item["rule"],
                "timestamp": time.time(),
            })

            # Cloud storage: upload critical frame
            if self._cloud_storage and item.get("frame_data"):
                try:
                    await self._cloud_storage.upload_frame(
                        device_id=device_id or "unknown",
                        frame_id=item["frame_id"],
                        frame_data=item["frame_data"],
                        metadata={"vlm_result": vlm_result[:100], "rule": item["rule"]},
                    )
                except Exception as ue:
                    logger.warning(f"Cloud upload failed: {ue}")

            # VLM-guided edge configuration
            if self._vlm_config_guide and device_id:
                await self._apply_vlm_guidance(vlm_result, device_id)

        except (asyncio.TimeoutError, Exception) as e:
            self._circuit_breaker.record_failure()
            vlm_requests_total.labels(status="error").inc()
            logger.error(f"VLM inference failed: {e}")
            if self._circuit_breaker.state == "open" and self._alert_manager:
                asyncio.create_task(
                    self._alert_manager.check_and_fire(
                        "circuit_breaker_open", {"error": str(e)}
                    )
                )
        finally:
            self._vlm_queue.task_done()

    async def _apply_vlm_guidance(self, vlm_result: str, device_id: str) -> None:
        """Apply VLM-guided edge configuration adjustments."""
        try:
            guidance = self._vlm_config_guide.parse_vlm_result(
                vlm_result, context={"device_id": device_id}
            )
            if guidance.should_apply and self._command_queue:
                for adj in guidance.adjustments:
                    self._command_id_counter += 1
                    cmd_dict = self._vlm_config_guide.create_control_command(
                        adj, device_id, self._command_id_counter
                    )
                    import neuro_pipeline_pb2 as pb
                    cmd = pb.ControlCommand(
                        type=cmd_dict["type"],
                        command_id=cmd_dict["command_id"],
                    )
                    for k, v in cmd_dict.get("parameters", {}).items():
                        if isinstance(v, str):
                            cmd.parameters[k] = v
                        elif isinstance(v, (int, float)):
                            cmd.parameters[k] = str(v)
                    await self._command_queue.put(cmd)
                    logger.info(
                        f"VLM-guided command sent: type={cmd.type}, "
                        f"device={device_id}, reason={adj.reason[:50]}"
                    )
        except Exception as ge:
            logger.warning(f"VLM config guide failed: {ge}")
