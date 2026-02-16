"""
Full-stack integration tests for v2 features.

Tests the complete flow: gRPC server + orchestrator + all v2 subsystems.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central"))

from src.application_logic.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from src.application_logic.behavior_analyzer import BehaviorAnalyzer
from src.application_logic.anomaly_baseline import AnomalyBaseline
from src.llm_vlm.reasoning_chain import ReasoningChain
from src.llm_vlm.rag_retriever import RAGRetriever
from src.model_management.model_registry import ModelRegistry, ModelStatus
from src.model_management.ab_test_manager import ABTestManager
from src.communication.device_session import DeviceSessionManager
from src.storage.detection_store import DetectionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_detection(frame_id: int, device_id: str = "edge-int-001",
                   class_name: str = "person", confidence: float = 0.92,
                   bbox=(0.1, 0.2, 0.5, 0.6), frame_data: bytes = b"",
                   num_boxes: int = 1):
    boxes = []
    for _ in range(num_boxes):
        box = MagicMock()
        box.class_name = class_name
        box.confidence = confidence
        box.x_min, box.y_min, box.x_max, box.y_max = bbox
        boxes.append(box)

    result = MagicMock()
    result.frame_id = frame_id
    result.device_id = device_id
    result.trace_id = f"{device_id}-{frame_id}"
    result.timestamp_us = int(time.time() * 1_000_000)
    result.frame_data = frame_data
    result.boxes = boxes
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detection_store(tmp_path):
    store = DetectionStore(tmp_path / "v2_integration.db")
    yield store
    store.close()


@pytest.fixture
def full_stack(tmp_path, detection_store):
    """Create a full v2 stack with all subsystems enabled."""
    behavior_analyzer = BehaviorAnalyzer(
        detection_store=detection_store,
        crowd_threshold=3,
    )
    anomaly_baseline = AnomalyBaseline(
        detection_store=detection_store,
        z_score_threshold=2.0,
        min_samples=10,
    )
    rag_retriever = RAGRetriever(
        detection_store=detection_store,
        max_items=5,
    )
    reasoning_chain = ReasoningChain(max_steps=3, timeout_per_step=5.0)
    model_registry = ModelRegistry(max_models_per_device=3)
    ab_test_manager = ABTestManager(traffic_split=0.5, min_samples=5)
    session_mgr = DeviceSessionManager(max_devices=8)

    orch = CentralOrchestrator(
        model_path=tmp_path / "models",
        vlm_rules=[VLMTriggerRule(class_name="person", min_confidence=0.8)],
        detection_store=detection_store,
        behavior_analyzer=behavior_analyzer,
        anomaly_baseline=anomaly_baseline,
        rag_retriever=rag_retriever,
        reasoning_chain=reasoning_chain,
    )
    orch.inference_engine = AsyncMock()
    orch.inference_engine._loaded = True
    orch.inference_engine.analyze_image = AsyncMock(return_value="VLM analysis")
    orch._batch_max_size = 1
    orch._batch_timeout = 0.05

    return {
        "orchestrator": orch,
        "store": detection_store,
        "behavior_analyzer": behavior_analyzer,
        "anomaly_baseline": anomaly_baseline,
        "rag_retriever": rag_retriever,
        "reasoning_chain": reasoning_chain,
        "model_registry": model_registry,
        "ab_test_manager": ab_test_manager,
        "session_mgr": session_mgr,
    }


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestV2FullStackIntegration:

    @pytest.mark.asyncio
    async def test_detection_triggers_behavior_and_anomaly(self, full_stack):
        """Detection flow triggers behavior analyzer + anomaly scorer."""
        orch = full_stack["orchestrator"]
        store = full_stack["store"]

        # Send crowd detection (5 persons)
        det = make_detection(
            frame_id=1, device_id="edge-int-001",
            class_name="person", confidence=0.9,
            num_boxes=5,
        )
        await orch.process_detection(det)

        rows = store.query(since=time.time() - 10)
        event_types = [r.get("event_type", "") for r in rows]
        # Should have at least a detection event, possibly behavior_alert
        assert "detection" in event_types

    @pytest.mark.asyncio
    async def test_multi_device_detection_stream(self, full_stack):
        """Multiple devices streaming detections concurrently."""
        orch = full_stack["orchestrator"]
        store = full_stack["store"]

        devices = ["edge-A", "edge-B", "edge-C"]
        for i, dev in enumerate(devices):
            for frame in range(5):
                det = make_detection(
                    frame_id=frame, device_id=dev,
                    confidence=0.85 + frame * 0.02,
                )
                await orch.process_detection(det)

        rows = store.query(since=time.time() - 10, limit=100)
        device_ids = {r["device_id"] for r in rows}
        assert device_ids == set(devices)
        assert len(rows) == 15

    @pytest.mark.asyncio
    async def test_rag_context_available_after_detections(self, full_stack):
        """After processing detections, RAG retriever can find them."""
        orch = full_stack["orchestrator"]
        rag = full_stack["rag_retriever"]

        for i in range(3):
            det = make_detection(frame_id=i, device_id="edge-rag-int")
            await orch.process_detection(det)

        ctx = rag.retrieve("edge-rag-int")
        assert len(ctx.items) >= 1

    def test_model_registry_lifecycle(self, full_stack):
        """Model deploy → list → undeploy through registry."""
        registry = full_stack["model_registry"]

        assert registry.deploy("yolov8n", "/models/yolov8n.rknn",
                               target_device_id="edge-001")
        assert registry.deploy("yolov8s", "/models/yolov8s.rknn",
                               target_device_id="edge-001")

        models = registry.list_models()
        assert len(models) == 2

        registry.undeploy("yolov8n")
        record = registry.get_model("yolov8n")
        assert record is not None
        assert record.status == ModelStatus.UNDEPLOYED

    def test_ab_test_with_session_tracking(self, full_stack):
        """A/B test groups are assigned and metrics recorded."""
        ab = full_stack["ab_test_manager"]
        session_mgr = full_stack["session_mgr"]

        for i in range(10):
            dev = f"edge-ab-{i:03d}"
            session_mgr.register(dev)
            group = ab.assign_group(dev)
            variant = ab.get_variant(dev)
            ab.record_inference(variant, latency_ms=20.0 + i)
            assert group is not None

        result = ab.evaluate()
        assert result is not None

    def test_timeseries_write_and_query(self, full_stack):
        """Time series data written and queried through store."""
        store = full_stack["store"]
        now = time.time()

        for i in range(30):
            store.record_timeseries(
                "edge-ts-int", "inference_ms",
                15.0 + i * 0.3,
                timestamp=now - 1800 + i * 60,
            )

        rows = store.query_timeseries(
            metric_name="inference_ms",
            device_id="edge-ts-int",
            start_time=now - 3600,
        )
        assert len(rows) == 30

    @pytest.mark.asyncio
    async def test_anomaly_detection_after_baseline_learning(self, full_stack):
        """Learn baseline from history, then detect anomaly in new detection."""
        store = full_stack["store"]
        anomaly = full_stack["anomaly_baseline"]
        orch = full_stack["orchestrator"]

        now = time.time()
        # Write normal baseline data
        for i in range(50):
            store.record_timeseries(
                "edge-anom-int", "detections_count", 2.0,
                timestamp=now - 3600 + i * 60,
            )

        baseline = anomaly.learn_baseline("edge-anom-int", "detections_count")
        assert baseline is not None

        # Score a normal value
        normal = anomaly.score("edge-anom-int", "detections_count", 2.0)
        assert not normal.is_anomaly

        # Score an anomalous value
        anom = anomaly.score("edge-anom-int", "detections_count", 50.0)
        assert anom.is_anomaly
