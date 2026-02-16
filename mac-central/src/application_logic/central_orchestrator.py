"""
Central orchestrator for coordinating edge events and VLM inference.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine
from src.llm_vlm.prompt_generator import PromptGenerator
from src.observability.metrics import (
    detections_total,
    vlm_requests_total,
    vlm_latency,
    vlm_queue_depth,
    events_stored,
    update_edge_metrics,
)
from src.observability.circuit_breaker import CircuitBreaker
from src.observability.alerting import AlertManager
from src.observability.tracing import span


@dataclass
class VLMTriggerRule:
    """Configurable rule for triggering VLM analysis."""
    class_name: str = "person"
    min_confidence: float = 0.8
    prompt_template: str = "person_behavior"


class CentralOrchestrator:
    """Orchestrates central server logic: event processing + VLM inference."""

    def __init__(
        self,
        model_path: Path,
        vlm_rules: Optional[List[VLMTriggerRule]] = None,
        detection_store=None,
        inference_mode: str = "llm",
        vlm_model_path: Optional[Path] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        alert_manager: Optional[AlertManager] = None,
        cloud_storage=None,
        batch_config=None,
        behavior_analyzer=None,
        reasoning_chain=None,
    ) -> None:
        self.model_path = model_path
        self.inference_engine: Optional[MLXInferenceEngine] = None
        self.prompt_generator = PromptGenerator()
        self._event_count = 0
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self.vlm_rules = vlm_rules or [VLMTriggerRule()]
        self._recent_events: deque = deque(maxlen=100)
        self._event_listeners: List[asyncio.Queue] = []
        self._detection_store = detection_store
        self._inference_mode = inference_mode
        self._vlm_model_path = vlm_model_path
        self._vlm_queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._vlm_worker_task: Optional[asyncio.Task] = None
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._alert_manager = alert_manager
        self._cloud_storage = cloud_storage
        self._batch_max_size = batch_config.max_size if batch_config else 8
        self._batch_timeout = batch_config.timeout_seconds if batch_config else 2.0
        self._shutting_down = False
        self._behavior_analyzer = behavior_analyzer
        self._reasoning_chain = reasoning_chain

    async def initialize(self) -> None:
        """Initialize orchestrator and load models."""
        logger.info("Initializing CentralOrchestrator...")
        self.inference_engine = MLXInferenceEngine(
            self.model_path,
            mode=self._inference_mode,
            vlm_model_path=self._vlm_model_path,
        )
        await self.inference_engine.load_model()
        self._vlm_worker_task = asyncio.create_task(self._vlm_worker())
        logger.info("CentralOrchestrator initialized successfully")

    async def process_detection(self, result: Any) -> Optional[str]:
        """Process detection result from edge device. VLM analysis is async-queued."""
        self._event_count += 1
        trace_id = getattr(result, "trace_id", f"unknown-{self._event_count}")
        device_id = getattr(result, "device_id", "")

        with span("process_detection", {
            "trace_id": trace_id,
            "device_id": device_id,
            "frame_id": str(result.frame_id),
            "box_count": str(len(result.boxes)),
        }):
            log = logger.bind(trace_id=trace_id) if hasattr(logger, "bind") else logger
            log.info(
                f"Processing detection #{self._event_count}: "
                f"frame_id={result.frame_id}, boxes={len(result.boxes)}, device={device_id}"
            )

            detections = []
            for box in result.boxes:
                detections_total.labels(class_name=box.class_name).inc()
                detections.append({
                    "class_name": box.class_name,
                    "confidence": box.confidence,
                    "x_min": box.x_min,
                    "y_min": box.y_min,
                    "x_max": box.x_max,
                    "y_max": box.y_max,
                })

            matched_rule = self._match_vlm_rule(detections)

            if matched_rule and self.inference_engine and result.frame_data:
                prompt = self.prompt_generator.generate(
                    detections, template=matched_rule.prompt_template
                )
                # Enqueue for async VLM processing (non-blocking)
                if self._shutting_down:
                    logger.warning("Shutting down, rejecting VLM request")
                else:
                    try:
                        self._vlm_queue.put_nowait({
                            "frame_data": result.frame_data,
                            "prompt": prompt,
                            "frame_id": result.frame_id,
                            "trace_id": trace_id,
                            "device_id": device_id,
                            "detections": detections,
                            "rule": matched_rule.class_name,
                        })
                    except asyncio.QueueFull:
                        vlm_requests_total.labels(status="dropped").inc()
                        logger.warning("VLM queue full, dropping analysis request")
                        if self._alert_manager:
                            asyncio.create_task(
                                self._alert_manager.check_and_fire("vlm_queue_full", {"frame_id": result.frame_id})
                            )
                vlm_queue_depth.set(self._vlm_queue.qsize())

            # Behavior analysis (v2)
            if self._behavior_analyzer and detections:
                try:
                    behavior_events = self._behavior_analyzer.analyze(
                        device_id, detections, timestamp=time.time()
                    )
                    for be in behavior_events:
                        self._record_event({
                            "type": "behavior_alert",
                            "device_id": device_id,
                            "behavior_type": be.behavior_type.value,
                            "confidence": be.confidence,
                            "description": be.description,
                            "timestamp": be.timestamp,
                        })
                except Exception as e:
                    logger.warning(f"Behavior analysis failed: {e}")

            self._record_event({
                "type": "detection",
                "frame_id": result.frame_id,
                "trace_id": trace_id,
                "device_id": device_id,
                "detections": detections,
                "timestamp": time.time(),
            })
            return None

    async def _vlm_worker(self) -> None:
        """Background worker that processes VLM analysis requests in batches."""
        logger.info("VLM worker started (batch mode)")
        batch_max = getattr(self, '_batch_max_size', 8)
        batch_timeout = getattr(self, '_batch_timeout', 2.0)

        while True:
            batch = []
            try:
                # Wait for first item
                item = await self._vlm_queue.get()
                batch.append(item)
                # Accumulate more items within timeout
                deadline = asyncio.get_event_loop().time() + batch_timeout
                while len(batch) < batch_max:
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
            if hasattr(self.inference_engine, 'batch_analyze') and len(batch) > 1:
                try:
                    batch_items = [{"frame_data": it["frame_data"], "prompt": it["prompt"]}
                                   for it in batch]
                    t0 = time.perf_counter()
                    batch_results = await asyncio.wait_for(
                        self.inference_engine.batch_analyze(batch_items),
                        timeout=30.0 * len(batch),
                    )
                    elapsed = time.perf_counter() - t0
                    logger.info(f"Batch VLM: {len(batch)} items in {elapsed*1000:.0f}ms")
                except Exception as e:
                    logger.warning(f"Batch inference failed, falling back to sequential: {e}")
                    batch_results = None

            # Process batch items (use batch results if available)
            for idx, item in enumerate(batch):
                if not self._circuit_breaker.allow_request():
                    vlm_requests_total.labels(status="circuit_open").inc()
                    logger.warning("Circuit breaker open, skipping VLM request")
                    self._vlm_queue.task_done()
                    continue

                try:
                    t0 = time.perf_counter()
                    device_id = item.get("device_id", "")
                    prompt = item["prompt"]
                    # Multi-turn: build prompt with conversation history
                    if device_id and self.inference_engine:
                        ctx = self.inference_engine.get_conversation(device_id)
                        prompt = ctx.build_prompt(prompt)
                    # Use batch result if available, otherwise run individually
                    with span("vlm_inference", {
                        "device_id": device_id,
                        "frame_id": str(item["frame_id"]),
                        "rule": item.get("rule", ""),
                    }):
                        if batch_results is not None and idx < len(batch_results):
                            vlm_result = batch_results[idx]
                        else:
                            vlm_result = await asyncio.wait_for(
                                self.inference_engine.analyze_image(
                                    item["frame_data"], prompt
                                ),
                                timeout=30.0,
                            )
                    # Record conversation turn
                    if device_id and self.inference_engine:
                        ctx = self.inference_engine.get_conversation(device_id)
                        ctx.add_turn("user", item["prompt"])
                        ctx.add_turn("assistant", vlm_result[:200])
                    elapsed = time.perf_counter() - t0
                    vlm_latency.observe(elapsed)
                    self._circuit_breaker.record_success()
                    vlm_requests_total.labels(status="success").inc()
                    logger.info(f"VLM result (frame {item['frame_id']}): {vlm_result[:100]}...")
                    self._record_event({
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

    def _match_vlm_rule(self, detections: list) -> Optional[VLMTriggerRule]:
        """Check if any detection matches a VLM trigger rule."""
        for rule in self.vlm_rules:
            if any(
                d["class_name"] == rule.class_name
                and d["confidence"] > rule.min_confidence
                for d in detections
            ):
                return rule
        return None

    async def send_command(self, command: Any) -> None:
        """Queue a control command for delivery to edge via event stream."""
        await self._command_queue.put(command)
        logger.info(f"Command queued: type={command.type}, id={command.command_id}")

    async def get_pending_command(self) -> Any:
        """Get next pending command (blocks until available)."""
        return await self._command_queue.get()

    async def handle_edge_event(self, event: Any) -> None:
        """Process an edge event received via bidirectional stream."""
        event_type = getattr(event, "type", None)
        device_id = ""
        metadata = {}

        # Extract metadata from protobuf map or dict
        if hasattr(event, "metadata"):
            raw = event.metadata
            metadata = dict(raw) if hasattr(raw, "items") else {}

        if hasattr(event, "device_id"):
            device_id = event.device_id
        else:
            device_id = metadata.get("device_id", "")

        logger.info(f"Edge event: type={event_type}, device={device_id}, desc={getattr(event, 'description', '')}")

        # Dispatch by event type
        # HEALTH_UPDATE = 1 in proto enum, but also check string/int
        type_val = event_type
        if hasattr(event_type, "value"):
            type_val = event_type.value
        elif hasattr(event_type, "name"):
            type_val = event_type.name

        if type_val in (1, "HEALTH_UPDATE", "health_update"):
            update_edge_metrics(device_id, metadata)
        elif type_val in (2, "SYSTEM_ERROR", "system_error"):
            logger.error(f"Edge system error from {device_id}: {metadata}")
            if self._alert_manager:
                asyncio.create_task(
                    self._alert_manager.check_and_fire(
                        "edge_system_error",
                        {"device_id": device_id, **metadata},
                    )
                )

    def is_ready(self) -> bool:
        """Check if orchestrator is ready to process requests."""
        return (
            self.inference_engine is not None
            and getattr(self.inference_engine, "_loaded", False)
        )

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown: drain VLM queue, then cancel worker."""
        logger.info(f"Shutting down (processed {self._event_count} events)...")
        self._shutting_down = True

        # Wait for VLM queue to drain
        if self._vlm_worker_task and not self._vlm_queue.empty():
            logger.info(f"Draining VLM queue ({self._vlm_queue.qsize()} items)...")
            try:
                await asyncio.wait_for(self._vlm_queue.join(), timeout=timeout)
                logger.info("VLM queue drained successfully")
            except asyncio.TimeoutError:
                remaining = self._vlm_queue.qsize()
                logger.warning(f"VLM drain timeout, {remaining} items discarded")

        if self._vlm_worker_task:
            self._vlm_worker_task.cancel()
            try:
                await self._vlm_worker_task
            except asyncio.CancelledError:
                pass
        if self.inference_engine:
            await self.inference_engine.unload_model()
        logger.info("CentralOrchestrator shutdown complete")

    def get_recent_events(self, limit: int = 50, device_id: str = "") -> List[Dict[str, Any]]:
        """Return recent detection events, optionally filtered by device_id."""
        events = list(self._recent_events)
        if device_id:
            events = [e for e in events if e.get("device_id") == device_id]
        return events[-limit:]

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to real-time event stream. Returns a queue that receives events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._event_listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe from event stream."""
        if q in self._event_listeners:
            self._event_listeners.remove(q)

    def _record_event(self, event: Dict[str, Any]) -> None:
        """Record event to in-memory buffer, DB, timeseries, and notify listeners."""
        self._recent_events.append(event)
        if self._detection_store:
            try:
                self._detection_store.record(event)
                events_stored.inc()
                # Write timeseries data points
                device_id = event.get("device_id", "")
                ts = event.get("timestamp", time.time())
                if event.get("type") == "detection" and event.get("detections"):
                    self._detection_store.record_timeseries(
                        device_id, "detections_count",
                        float(len(event["detections"])), ts
                    )
                if event.get("type") == "vlm_analysis":
                    self._detection_store.record_timeseries(
                        device_id, "vlm_analyses_count", 1.0, ts
                    )
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")
        for q in self._event_listeners:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
