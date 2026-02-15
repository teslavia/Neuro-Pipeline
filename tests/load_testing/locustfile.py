"""
Locust load test for gRPC streaming — simulates N edge devices.

Usage:
    locust -f tests/load_testing/locustfile.py --headless -u 4 -r 1 -t 30s
"""

import random
import time
import grpc
from locust import User, task, between, events

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))

from generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc


class GRPCEdgeUser(User):
    """Simulates an edge device streaming detections via gRPC."""

    wait_time = between(0.01, 0.05)  # ~20-100 FPS
    host = "localhost:50051"

    def on_start(self):
        self.device_id = f"edge-load-{self.environment.runner.user_count:03d}"
        self.channel = grpc.insecure_channel(self.host)
        self.stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(self.channel)
        self.frame_count = 0

    def on_stop(self):
        if self.channel:
            self.channel.close()

    @task(10)
    def stream_detection(self):
        """Send a single detection result."""
        self.frame_count += 1
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = self.frame_count
        result.device_id = self.device_id
        result.trace_id = f"{self.device_id}-{self.frame_count}"
        result.timestamp_us = int(time.time() * 1_000_000)

        # Random detection
        box = result.boxes.add()
        box.class_name = random.choice(["person", "car", "dog"])
        box.confidence = random.uniform(0.5, 0.99)
        box.x_min = random.uniform(0.0, 0.5)
        box.y_min = random.uniform(0.0, 0.5)
        box.x_max = box.x_min + random.uniform(0.1, 0.4)
        box.y_max = box.y_min + random.uniform(0.1, 0.4)

        t0 = time.perf_counter()
        try:
            def gen():
                yield result
            resp = self.stub.StreamDetectionResults(gen())
            elapsed_ms = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="gRPC",
                name="StreamDetectionResults",
                response_time=elapsed_ms,
                response_length=0,
                exception=None,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="gRPC",
                name="StreamDetectionResults",
                response_time=elapsed_ms,
                response_length=0,
                exception=e,
            )

    @task(1)
    def health_check(self):
        """Periodic health check."""
        t0 = time.perf_counter()
        try:
            req = neuro_pipeline_pb2.HealthCheckRequest(client_id=self.device_id)
            resp = self.stub.HealthCheck(req)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="gRPC",
                name="HealthCheck",
                response_time=elapsed_ms,
                response_length=0,
                exception=None,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="gRPC",
                name="HealthCheck",
                response_time=elapsed_ms,
                response_length=0,
                exception=e,
            )
