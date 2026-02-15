"""Tests for tracing module."""

import pytest
from unittest.mock import patch, MagicMock

from src.observability.tracing import init_tracing, span, get_tracer


class TestTracing:
    def test_init_without_otel(self):
        """Tracing degrades gracefully without opentelemetry."""
        import src.observability.tracing as t
        t._initialized = False
        t._tracer = None
        with patch.dict("sys.modules", {"opentelemetry": None}):
            result = init_tracing()
        assert result is False

    def test_span_noop_without_tracer(self):
        """span() yields None when tracing is not available."""
        import src.observability.tracing as t
        t._tracer = None
        with span("test-span") as s:
            assert s is None

    def test_get_tracer_returns_none_initially(self):
        import src.observability.tracing as t
        t._tracer = None
        assert get_tracer() is None

    def test_span_with_mock_tracer(self):
        """span() creates a real span when tracer is available."""
        import src.observability.tracing as t
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = lambda _: mock_span
        mock_tracer.start_as_current_span.return_value.__exit__ = lambda *_: None
        t._tracer = mock_tracer
        with span("test-span", {"key": "value"}) as s:
            assert s is mock_span
        t._tracer = None  # cleanup
