"""Tests for gRPC input validation."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from communication.grpc_server import NeuroPipelineServicer


class FakeBox:
    def __init__(self, class_name="person", confidence=0.9,
                 x_min=0.1, y_min=0.2, x_max=0.5, y_max=0.6):
        self.class_name = class_name
        self.confidence = confidence
        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max


class FakeResult:
    def __init__(self, device_id="edge-001", boxes=None):
        self.device_id = device_id
        self.boxes = boxes or []
        self.frame_id = 1


def test_valid_input_passes():
    result = FakeResult(boxes=[FakeBox()])
    assert NeuroPipelineServicer._validate_detection(result) is None


def test_empty_device_id_rejected():
    result = FakeResult(device_id="")
    err = NeuroPipelineServicer._validate_detection(result)
    assert err is not None
    assert "device_id" in err


def test_negative_coordinate_rejected():
    result = FakeResult(boxes=[FakeBox(x_min=-0.1)])
    err = NeuroPipelineServicer._validate_detection(result)
    assert err is not None
    assert "x_min" in err


def test_confidence_above_one_rejected():
    result = FakeResult(boxes=[FakeBox(confidence=1.5)])
    err = NeuroPipelineServicer._validate_detection(result)
    assert err is not None
    assert "confidence" in err


def test_missing_boxes_passes():
    """Result with no boxes should pass validation."""
    result = FakeResult(boxes=[])
    assert NeuroPipelineServicer._validate_detection(result) is None
