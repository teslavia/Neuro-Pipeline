"""OpenTelemetry tracing initialization with graceful degradation.

Lazy-loads OTel SDK. If not installed, provides no-op span utilities.
"""

import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_tracer = None
_initialized = False


def init_tracing(
    service_name: str = "neuro-pipeline-central",
    endpoint: str = "http://localhost:4317",
    sample_rate: float = 1.0,
) -> bool:
    """Initialize OpenTelemetry tracing. Returns True if successful."""
    global _tracer, _initialized
    if _initialized:
        return _tracer is not None
    _initialized = True

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        resource = Resource.create({"service.name": service_name})
        sampler = TraceIdRatioBased(sample_rate)
        provider = TracerProvider(resource=resource, sampler=sampler)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        logger.info(f"OTel tracing initialized: endpoint={endpoint}")
        return True
    except ImportError:
        logger.warning("opentelemetry not installed, tracing disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to init tracing: {e}")
        return False


def get_tracer():
    """Get the global tracer (may be None if OTel not available)."""
    return _tracer


@contextmanager
def span(name: str, attributes: Optional[dict] = None):
    """Context manager for creating a trace span. No-op if tracing unavailable."""
    if _tracer:
        with _tracer.start_as_current_span(name) as s:
            if attributes:
                for k, v in attributes.items():
                    s.set_attribute(k, str(v))
            yield s
    else:
        yield None
