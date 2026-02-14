"""
Central orchestrator for coordinating edge events and VLM inference.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine
from src.llm_vlm.prompt_generator import PromptGenerator


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
    ) -> None:
        self.model_path = model_path
        self.inference_engine: Optional[MLXInferenceEngine] = None
        self.prompt_generator = PromptGenerator()
        self._event_count = 0
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self.vlm_rules = vlm_rules or [VLMTriggerRule()]

    async def initialize(self) -> None:
        """Initialize orchestrator and load models."""
        logger.info("Initializing CentralOrchestrator...")
        self.inference_engine = MLXInferenceEngine(self.model_path)
        await self.inference_engine.load_model()
        logger.info("CentralOrchestrator initialized successfully")

    async def process_detection(self, result: Any) -> Optional[str]:
        """Process detection result from edge device."""
        self._event_count += 1
        trace_id = getattr(result, "trace_id", f"unknown-{self._event_count}")
        log = logger.bind(trace_id=trace_id) if hasattr(logger, "bind") else logger
        log.info(
            f"Processing detection #{self._event_count}: "
            f"frame_id={result.frame_id}, boxes={len(result.boxes)}"
        )

        detections = []
        for box in result.boxes:
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
            vlm_result = await self.inference_engine.analyze_image(
                result.frame_data, prompt
            )
            logger.info(f"VLM analysis result: {vlm_result[:100]}...")
            return vlm_result

        return None

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
        logger.info(f"Edge event: type={event.type}, desc={event.description}")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info(f"Shutting down (processed {self._event_count} events)...")
        if self.inference_engine:
            await self.inference_engine.unload_model()
        logger.info("CentralOrchestrator shutdown complete")
