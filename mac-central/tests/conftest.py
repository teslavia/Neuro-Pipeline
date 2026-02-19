"""
Pytest configuration and shared fixtures for Neuro-Pipeline tests.
"""

import pytest

from tests.factories import make_detection_result


@pytest.fixture
def mock_detection_result():
    """Mock DetectionResult protobuf message."""
    return make_detection_result()


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
