"""Tests for OTel tracing integration in orchestrator hot paths."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from observability.tracing import span


def test_span_creates_when_tracer_available():
    """span() should create a real span when tracer is set."""
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    with patch("observability.tracing._tracer", mock_tracer):
        with span("test_op", {"key": "val"}) as s:
            assert s is mock_span
            mock_span.set_attribute.assert_called_with("key", "val")


def test_span_noop_without_tracer():
    """span() should yield None when no tracer is configured."""
    with patch("observability.tracing._tracer", None):
        with span("test_op", {"key": "val"}) as s:
            assert s is None


def test_span_attributes_propagated():
    """Span attributes should be set from the dict."""
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    with patch("observability.tracing._tracer", mock_tracer):
        with span("op", {"device_id": "edge-001", "frame_id": "42"}):
            pass
    calls = {c[0][0]: c[0][1] for c in mock_span.set_attribute.call_args_list}
    assert calls["device_id"] == "edge-001"
    assert calls["frame_id"] == "42"
