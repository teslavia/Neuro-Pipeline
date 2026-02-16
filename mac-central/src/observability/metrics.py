"""Prometheus metrics definitions for Neuro-Pipeline."""

from prometheus_client import Counter, Gauge, Histogram, Info

# --- Counters ---
detections_total = Counter(
    "np_detections_total", "Total detections received", ["class_name"]
)
vlm_requests_total = Counter(
    "np_vlm_requests_total", "VLM analysis requests", ["status"]
)
grpc_requests_total = Counter(
    "np_grpc_requests_total", "gRPC requests", ["method", "status"]
)

# --- Histograms ---
grpc_latency = Histogram(
    "np_grpc_latency_seconds", "gRPC processing latency", ["method"]
)
vlm_latency = Histogram("np_vlm_latency_seconds", "VLM inference latency")

# --- Gauges ---
vlm_queue_depth = Gauge("np_vlm_queue_depth", "Current VLM queue size")
edge_connections = Gauge("np_edge_connections", "Active edge connections")
events_stored = Gauge("np_events_stored_total", "Total events in SQLite")
edge_device_status = Gauge(
    "np_edge_device_status", "Edge device status (1=connected, 0=disconnected)", ["device_id"]
)

# --- Edge metrics (reported via gRPC health updates) ---
edge_frames_processed = Gauge(
    "np_edge_frames_processed", "Edge frames processed", ["device_id"]
)
edge_detections_total = Gauge(
    "np_edge_detections_total", "Edge detections total", ["device_id"]
)
edge_inference_errors = Gauge(
    "np_edge_inference_errors", "Edge inference errors", ["device_id"]
)
edge_fps = Gauge("np_edge_fps", "Edge current FPS", ["device_id"])
edge_inference_latency_avg = Gauge(
    "np_edge_inference_latency_avg_ms", "Edge avg inference latency ms", ["device_id"]
)

# --- Info ---
build_info = Info("np_build", "Build information")


def update_edge_metrics(device_id: str, metadata: dict) -> None:
    """Update edge Prometheus gauges from health update metadata."""
    if not device_id:
        return
    _safe_set(edge_frames_processed, device_id, metadata.get("frames_processed"))
    _safe_set(edge_detections_total, device_id, metadata.get("detections_total"))
    _safe_set(edge_inference_errors, device_id, metadata.get("inference_errors"))
    _safe_set(edge_fps, device_id, metadata.get("fps"))
    _safe_set(edge_inference_latency_avg, device_id, metadata.get("inference_latency_avg_ms"))


def _safe_set(gauge, device_id: str, value) -> None:
    if value is not None:
        try:
            gauge.labels(device_id=device_id).set(float(value))
        except (ValueError, TypeError):
            pass
