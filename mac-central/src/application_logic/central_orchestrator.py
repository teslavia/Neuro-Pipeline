"""
Central orchestrator for coordinating edge events and VLM inference.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine
from src.llm_vlm.prompt_generator import PromptGenerator

logger = logging.getLogger(__name__)


class CentralOrchestrator:
    """Orchestrates central server logic: event processing + VLM inference."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.inference_engine: Optional[MLXInferenceEngine] = None
        self.prompt_generator = PromptGenerator()
        self._event_count = 0

    async def initialize(self) -> None:
        """Initialize orchestrator and load models."""
        logger.info("Initializing CentralOrchestrator...")
        self.inference_engine = MLXInferenceEngine(self.model_path)
        await self.inference_engine.load_model()
        logger.info("CentralOrchestrator initialized successfully")

    async def process_detection(self, result: Any) -> Optional[str]:
        """
        Process detection result from edge device.

        Args:
            result: DetectionResult protobuf message.

        Returns:
            VLM analysis result if triggered, None otherwise.
        """
        self._event_count += 1
        logger.info(
            f"Processing detection #{self._event_count}: "
            f"frame_id={result.frame_id}, boxes={len(result.boxes)}"
        )

        # Extract detections as dicts
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

        # Check if VLM analysis is needed (e.g., person detected with high confidence)
        should_analyze = any(
            d["class_name"] == "person" and d["confidence"] > 0.8
            for d in detections
        )

        if should_analyze and self.inference_engine and result.frame_data:
            # Generate prompt and run VLM
            prompt = self.prompt_generator.generate(
                detections, template="person_behavior"
            )
            vlm_result = await self.inference_engine.analyze_image(
                result.frame_data, prompt
            )
            logger.info(f"VLM analysis result: {vlm_result[:100]}...")
            return vlm_result

        return None

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info(f"Shutting down (processed {self._event_count} events)...")
        if self.inference_engine:
            await self.inference_engine.unload_model()
        logger.info("CentralOrchestrator shutdown complete")
