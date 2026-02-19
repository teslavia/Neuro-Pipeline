"""
Central orchestrator — thin coordinator delegating to EventBus,
DetectionProcessor, and VLMProcessingPipeline.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.logging import get_logger
from src.core.event_bus import EventBus
from src.inference.mlx_llm_inference import MLXInferenceEngine
from src.inference.prompt_generator import PromptGenerator
from src.inference.vlm_config_guide import VLMConfigGuide
from src.observability.circuit_breaker import CircuitBreaker
from src.observability.alerting import AlertManager
from src.observability.metrics import update_edge_metrics
from src.pipeline.detection_processor import DetectionProcessor
from src.pipeline.vlm_pipeline import VLMProcessingPipeline

logger = get_logger(__name__)


@dataclass
class VLMTriggerRule:
    """Configurable rule for triggering VLM analysis."""
    class_name: str = "person"
    min_confidence: float = 0.8
    prompt_template: str = "person_behavior"


class CentralOrchestrator:
    """Thin coordinator — public API unchanged, internals delegated."""

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
        rag_retriever=None,
        anomaly_baseline=None,
        vlm_config_guide: Optional[VLMConfigGuide] = None,
    ) -> None:
        self.model_path = model_path
        self._inference_engine: Optional[MLXInferenceEngine] = None
        self._inference_mode = inference_mode
        self._vlm_model_path = vlm_model_path
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._vlm_queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._alert_manager = alert_manager

        # Sub-components (must be created before _shutting_down property is usable)
        self._event_bus = EventBus(detection_store)
        self._detection_processor = DetectionProcessor(
            event_bus=self._event_bus,
            vlm_queue=self._vlm_queue,
            vlm_rules=vlm_rules or [VLMTriggerRule()],
            behavior_analyzer=behavior_analyzer,
            anomaly_baseline=anomaly_baseline,
            alert_manager=alert_manager,
            prompt_generator=PromptGenerator(),
        )

        batch_max = batch_config.max_size if batch_config else 8
        batch_timeout = batch_config.timeout_seconds if batch_config else 2.0
        self._vlm_pipeline = VLMProcessingPipeline(
            vlm_queue=self._vlm_queue,
            inference_engine=None,  # set after load_model
            event_bus=self._event_bus,
            circuit_breaker=circuit_breaker or CircuitBreaker(),
            alert_manager=alert_manager,
            cloud_storage=cloud_storage,
            rag_retriever=rag_retriever,
            vlm_config_guide=vlm_config_guide,
            batch_max_size=batch_max,
            batch_timeout=batch_timeout,
        )
        self._vlm_pipeline.set_command_queue(self._command_queue)

    # -- Compatibility shims for tests accessing internals --

    @property
    def _vlm_worker_task(self):
        return self._vlm_pipeline._worker_task

    @_vlm_worker_task.setter
    def _vlm_worker_task(self, val):
        self._vlm_pipeline._worker_task = val

    @property
    def _shutting_down(self):
        return self._detection_processor._shutting_down

    @_shutting_down.setter
    def _shutting_down(self, val):
        self._detection_processor._shutting_down = val

    @property
    def _event_listeners(self):
        return self._event_bus._listeners

    @property
    def inference_engine(self):
        return self._inference_engine

    @inference_engine.setter
    def inference_engine(self, engine):
        self._inference_engine = engine
        if hasattr(self, '_detection_processor'):
            self._detection_processor._inference_engine = engine
        if hasattr(self, '_vlm_pipeline'):
            self._vlm_pipeline._inference_engine = engine

    @property
    def _batch_max_size(self):
        return self._vlm_pipeline._batch_max_size

    @_batch_max_size.setter
    def _batch_max_size(self, val):
        self._vlm_pipeline._batch_max_size = val

    @property
    def _batch_timeout(self):
        return self._vlm_pipeline._batch_timeout

    @_batch_timeout.setter
    def _batch_timeout(self, val):
        self._vlm_pipeline._batch_timeout = val

    def _match_vlm_rule(self, detections):
        return self._detection_processor._match_vlm_rule(detections)

    async def _vlm_worker(self):
        return await self._vlm_pipeline._worker()

    # -- Public property for hot-reload compatibility --
    @property
    def vlm_rules(self):
        return self._detection_processor.vlm_rules

    @vlm_rules.setter
    def vlm_rules(self, rules):
        self._detection_processor.vlm_rules = rules

    async def initialize(self) -> None:
        """Initialize orchestrator and load models."""
        logger.info("Initializing CentralOrchestrator...")
        self.inference_engine = MLXInferenceEngine(
            self.model_path,
            mode=self._inference_mode,
            vlm_model_path=self._vlm_model_path,
        )
        await self.inference_engine.load_model()
        await self._vlm_pipeline.start()
        logger.info("CentralOrchestrator initialized successfully")

    async def process_detection(self, result: Any) -> Optional[str]:
        """Process detection result from edge device."""
        return await self._detection_processor.process(result)

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

        if hasattr(event, "metadata"):
            raw = event.metadata
            metadata = dict(raw) if hasattr(raw, "items") else {}

        if hasattr(event, "device_id"):
            device_id = event.device_id
        else:
            device_id = metadata.get("device_id", "")

        logger.info(f"Edge event: type={event_type}, device={device_id}")

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
        """Graceful shutdown."""
        count = self._detection_processor.event_count
        logger.info(f"Shutting down (processed {count} events)...")
        self._detection_processor._shutting_down = True
        await self._vlm_pipeline.shutdown(timeout)
        if self.inference_engine:
            await self.inference_engine.unload_model()
        logger.info("CentralOrchestrator shutdown complete")

    # -- Delegated event bus methods (public API unchanged) --

    def get_recent_events(self, limit: int = 50, device_id: str = "") -> List[Dict[str, Any]]:
        return self._event_bus.get_recent(limit, device_id)

    def subscribe(self) -> asyncio.Queue:
        return self._event_bus.subscribe()

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._event_bus.unsubscribe(q)
