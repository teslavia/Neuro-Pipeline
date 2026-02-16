"""Tests for Prometheus metrics."""

import pytest
from prometheus_client import CollectorRegistry

from src.observability.metrics import (
    build_info,
    detections_total,
    edge_connections,
    events_stored,
    grpc_latency,
    grpc_requests_total,
    vlm_latency,
    vlm_queue_depth,
    vlm_requests_total,
)


def test_counter_increment():
    """Counters can be incremented by label."""
    before = detections_total.labels(class_name="person")._value.get()
    detections_total.labels(class_name="person").inc()
    after = detections_total.labels(class_name="person")._value.get()
    assert after == before + 1


def test_vlm_requests_counter():
    before = vlm_requests_total.labels(status="success")._value.get()
    vlm_requests_total.labels(status="success").inc()
    assert vlm_requests_total.labels(status="success")._value.get() == before + 1


def test_grpc_requests_counter():
    before = grpc_requests_total.labels(method="StreamDetectionResults", status="ok")._value.get()
    grpc_requests_total.labels(method="StreamDetectionResults", status="ok").inc()
    after = grpc_requests_total.labels(method="StreamDetectionResults", status="ok")._value.get()
    assert after == before + 1


def test_histogram_observe():
    """Histograms record observations."""
    grpc_latency.labels(method="StreamDetectionResults").observe(0.05)
    vlm_latency.observe(1.5)


def test_gauge_set():
    """Gauges can be set to arbitrary values."""
    vlm_queue_depth.set(5)
    assert vlm_queue_depth._value.get() == 5
    edge_connections.set(2)
    assert edge_connections._value.get() == 2
    events_stored.set(100)
    assert events_stored._value.get() == 100


def test_build_info():
    """Info metric can be set."""
    build_info.info({"version": "1.2.0", "branch": "main"})
