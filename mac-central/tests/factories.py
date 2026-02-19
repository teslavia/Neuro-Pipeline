"""Test factories for common mock objects.

Centralizes repeated mock construction patterns to reduce boilerplate
across test files. Import and call these instead of inline MagicMock setup.
"""

import asyncio
from typing import Any, AsyncIterator, Optional, Sequence
from unittest.mock import AsyncMock, MagicMock

from src.generated import neuro_pipeline_pb2


def make_box(
    class_name: str = "person",
    confidence: float = 0.95,
    x_min: float = 0.2,
    y_min: float = 0.3,
    x_max: float = 0.8,
    y_max: float = 0.9,
    class_id: int = 0,
) -> MagicMock:
    """Create a mock bounding box."""
    box = MagicMock()
    box.class_id = class_id
    box.class_name = class_name
    box.confidence = confidence
    box.x_min = x_min
    box.y_min = y_min
    box.x_max = x_max
    box.y_max = y_max
    return box


def make_detection_result(
    frame_id: int = 12345,
    device_id: str = "edge-test",
    boxes: Optional[list] = None,
    frame_data: bytes = b"",
    timestamp_us: int = 1234567890000000,
    cpu_usage: float = 45.2,
    npu_usage: float = 78.5,
    memory_used_mb: float = 256.0,
    temperature_c: float = 55.0,
    fps: int = 30,
) -> MagicMock:
    """Create a mock DetectionResult with metrics."""
    result = MagicMock()
    result.frame_id = frame_id
    result.device_id = device_id
    result.timestamp_us = timestamp_us
    result.frame_data = frame_data

    if boxes is None:
        boxes = [make_box()]
    result.boxes = boxes

    metrics = MagicMock()
    metrics.cpu_usage = cpu_usage
    metrics.npu_usage = npu_usage
    metrics.memory_used_mb = memory_used_mb
    metrics.temperature_c = temperature_c
    metrics.fps = fps
    result.metrics = metrics

    return result


def make_orchestrator(**overrides: Any) -> MagicMock:
    """Create a mock CentralOrchestrator with standard async methods."""
    orch = MagicMock()
    orch.process_detection = AsyncMock()
    orch.send_command = AsyncMock()
    orch.handle_edge_event = AsyncMock()
    orch.get_pending_command = AsyncMock(side_effect=asyncio.TimeoutError)
    orch.inference_engine = MagicMock()
    orch.inference_engine.load_model = AsyncMock()
    orch.inference_engine.unload_model = AsyncMock()
    orch.inference_engine.analyze_image = AsyncMock(return_value="VLM analysis result")
    for k, v in overrides.items():
        setattr(orch, k, v)
    return orch


async def make_detection_stream(
    count: int = 3,
    device_id: str = "edge-test",
) -> AsyncIterator[neuro_pipeline_pb2.DetectionResult]:
    """Yield `count` protobuf DetectionResult messages."""
    for i in range(count):
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = i
        result.device_id = device_id
        yield result
