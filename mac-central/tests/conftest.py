"""
Pytest configuration and shared fixtures for Neuro-Pipeline tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add repo root for extensions/ imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_detection_result():
    """Mock DetectionResult protobuf message."""
    result = MagicMock()
    result.frame_id = 12345
    result.timestamp_us = 1234567890000000
    result.frame_data = b""

    box = MagicMock()
    box.class_id = 0
    box.class_name = "person"
    box.confidence = 0.95
    box.x_min = 0.2
    box.y_min = 0.3
    box.x_max = 0.8
    box.y_max = 0.9

    result.boxes = [box]

    metrics = MagicMock()
    metrics.cpu_usage = 45.2
    metrics.npu_usage = 78.5
    metrics.memory_used_mb = 256.0
    metrics.temperature_c = 55.0
    metrics.fps = 30
    result.metrics = metrics

    return result


@pytest.fixture
def mock_detection_with_frame(mock_detection_result):
    """Mock DetectionResult with JPEG frame data."""
    mock_detection_result.frame_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    return mock_detection_result


@pytest.fixture
def sample_detections():
    """Sample detection dicts for prompt generator tests."""
    return [
        {
            "class_name": "person",
            "confidence": 0.95,
            "x_min": 0.2,
            "y_min": 0.3,
            "x_max": 0.8,
            "y_max": 0.9,
        },
        {
            "class_name": "car",
            "confidence": 0.87,
            "x_min": 0.5,
            "y_min": 0.6,
            "x_max": 0.9,
            "y_max": 0.95,
        },
    ]


@pytest.fixture
def temp_model_dir(tmp_path):
    """Create temporary model directory."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    return model_dir
