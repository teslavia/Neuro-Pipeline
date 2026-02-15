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

# --- Info ---
build_info = Info("np_build", "Build information")
