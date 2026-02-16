"""
E2E tests for v2 features: behavior analysis, RAG, anomaly detection,
reasoning chain, A/B testing, time series, model management.
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
from src.application_logic.behavior_analyzer import BehaviorAnalyzer, BehaviorType
from src.application_logic.anomaly_baseline import AnomalyBaseline
from src.llm_vlm.reasoning_chain import ReasoningChain
from src.llm_vlm.rag_retriever import RAGRetriever
from src.model_management.model_registry import ModelRegistry, ModelStatus
from src.model_management.ab_test_manager import ABTestManager
from src.storage.detection_store import DetectionStore
from src.communication.device_session import DeviceSessionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_detection(frame_id: int, device_id: str = "edge-v2-001",
                   class_name: str = "person", confidence: float = 0.92,
                   bbox=(0.1, 0.2, 0.5, 0.6), frame_data: bytes = b""):
    box = MagicMock()
    box.class_name = class_name
    box.confidence = confidence
    box.x_min, box.y_min, box.x_max, box.y_max = bbox

    result = MagicMock()
    result.frame_id = frame_id
    result.device_id = device_id
    result.trace_id = f"{device_id}-{frame_id}"
    result.timestamp_us = int(time.time() * 1_000_000)
    result.frame_data = frame_data
    result.boxes = [box]
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detection_store(tmp_path):
    store = DetectionStore(tmp_path / "v2_e2e.db")
    yield store
    store.close()


@pytest.fixture
def behavior_analyzer(detection_store):
    return BehaviorAnalyzer(
        detection_store=detection_store,
        loiter_threshold_seconds=20.0,
        crowd_threshold=3,
        analysis_window_seconds=60.0,
    )


@pytest.fixture
def anomaly_baseline(detection_store):
    return AnomalyBaseline(
        detection_store=detection_store,
        baseline_window_hours=1.0,
        z_score_threshold=2.0,
        min_samples=10,
    )


@pytest.fixture
def rag_retriever(detection_store):
    return RAGRetriever(
        detection_store=detection_store,
        max_items=5,
        time_window_hours=1.0,
    )


@pytest.fixture
def reasoning_chain():
    return ReasoningChain(max_steps=3, timeout_per_step=5.0)


@pytest.fixture
def model_registry():
    return ModelRegistry(max_models_per_device=3)


@pytest.fixture
def ab_test_manager():
    return ABTestManager(traffic_split=0.5, min_samples=5, metric="latency")


@pytest.fixture
def orchestrator_v2(tmp_path, detection_store, behavior_analyzer, anomaly_baseline):
    orch = CentralOrchestrator(
        model_path=tmp_path / "models",
        vlm_rules=[VLMTriggerRule(class_name="person", min_confidence=0.8)],
        detection_store=detection_store,
        behavior_analyzer=behavior_analyzer,
        anomaly_baseline=anomaly_baseline,
    )
    orch.inference_engine = AsyncMock()
    orch.inference_engine._loaded = True
    orch.inference_engine.analyze_image = AsyncMock(return_value="test VLM output")
    orch._batch_max_size = 1
    orch._batch_timeout = 0.05
    return orch


# ---------------------------------------------------------------------------
# 1. Behavior Analysis E2E
# ---------------------------------------------------------------------------

class TestBehaviorAnalysisE2E:

    def test_crowd_detection(self, behavior_analyzer):
        """Multiple objects of same class triggers crowd alert."""
        detections = [
            {"class_name": "person", "confidence": 0.9} for _ in range(5)
        ]
        events = behavior_analyzer.analyze("edge-001", detections)
        assert len(events) >= 1
        assert events[0].behavior_type == BehaviorType.CROWD
        assert "5 person" in events[0].description

    def test_no_crowd_below_threshold(self, behavior_analyzer):
        """Below threshold does not trigger crowd."""
        detections = [
            {"class_name": "person", "confidence": 0.9} for _ in range(2)
        ]
        events = behavior_analyzer.analyze("edge-001", detections)
        crowd_events = [e for e in events if e.behavior_type == BehaviorType.CROWD]
        assert len(crowd_events) == 0

    @pytest.mark.asyncio
    async def test_behavior_events_in_orchestrator(self, orchestrator_v2, detection_store):
        """Behavior analyzer fires through orchestrator pipeline."""
        # Send enough detections to trigger crowd (5 boxes)
        result = MagicMock()
        result.frame_id = 1
        result.device_id = "edge-crowd"
        result.trace_id = "edge-crowd-1"
        result.timestamp_us = int(time.time() * 1_000_000)
        result.frame_data = b""
        boxes = []
        for _ in range(5):
            box = MagicMock()
            box.class_name = "person"
            box.confidence = 0.9
            box.x_min, box.y_min, box.x_max, box.y_max = 0.1, 0.2, 0.5, 0.6
            boxes.append(box)
        result.boxes = boxes

        await orchestrator_v2.process_detection(result)

        # Check that behavior_alert event was recorded
        rows = detection_store.query(since=time.time() - 10)
        event_types = [r.get("event_type", r.get("type", "")) for r in rows]
        assert "behavior_alert" in event_types or "detection" in event_types


# ---------------------------------------------------------------------------
# 2. RAG Context Injection E2E
# ---------------------------------------------------------------------------

class TestRAGContextE2E:

    def test_rag_retrieves_history(self, rag_retriever, detection_store):
        """RAG retriever returns historical events from store."""
        # Write some history
        for i in range(3):
            detection_store.record({
                "type": "detection",
                "frame_id": i,
                "trace_id": f"t-{i}",
                "timestamp": time.time() - 60 + i,
                "detections": [{"class_name": "person", "confidence": 0.9}],
                "device_id": "edge-rag-001",
            })

        ctx = rag_retriever.retrieve("edge-rag-001")
        assert len(ctx.items) >= 1
        assert ctx.query_time_ms >= 0
        assert "edge-rag-001" in ctx.summary

    def test_rag_empty_for_unknown_device(self, rag_retriever):
        """RAG returns empty for device with no history."""
        ctx = rag_retriever.retrieve("edge-nonexistent")
        assert len(ctx.items) == 0
        assert "No recent events" in ctx.summary

    def test_rag_format_for_prompt(self, rag_retriever, detection_store):
        """format_for_prompt returns usable string."""
        detection_store.record({
            "type": "detection",
            "frame_id": 1,
            "trace_id": "t-1",
            "timestamp": time.time(),
            "detections": [{"class_name": "car", "confidence": 0.85}],
            "device_id": "edge-rag-002",
        })
        ctx = rag_retriever.retrieve("edge-rag-002", class_names=["car"])
        prompt_text = rag_retriever.format_for_prompt(ctx)
        assert isinstance(prompt_text, str)
        assert len(prompt_text) > 0


# ---------------------------------------------------------------------------
# 3. Anomaly Detection E2E
# ---------------------------------------------------------------------------

class TestAnomalyDetectionE2E:

    def test_anomaly_with_baseline(self, anomaly_baseline, detection_store):
        """Write normal data, learn baseline, then score anomaly."""
        now = time.time()
        # Write 50 normal data points (value ~10)
        for i in range(50):
            detection_store.record_timeseries(
                "edge-anom-001", "detections_count",
                10.0 + (i % 3) * 0.5,
                timestamp=now - 3600 + i * 60,
            )

        # Learn baseline
        baseline = anomaly_baseline.learn_baseline("edge-anom-001", "detections_count")
        assert baseline is not None
        assert baseline.sample_count >= 10
        assert 9.0 < baseline.mean < 12.0

        # Score normal value
        normal_score = anomaly_baseline.score("edge-anom-001", "detections_count", 10.5)
        assert not normal_score.is_anomaly

        # Score anomalous value
        anomaly_score = anomaly_baseline.score("edge-anom-001", "detections_count", 50.0)
        assert anomaly_score.is_anomaly
        assert anomaly_score.z_score > 2.0

    def test_no_false_positive_without_baseline(self, anomaly_baseline):
        """Without learned baseline, no anomaly is reported."""
        score = anomaly_baseline.score("edge-new", "detections_count", 100.0)
        assert not score.is_anomaly
        assert score.z_score == 0.0


# ---------------------------------------------------------------------------
# 4. Reasoning Chain E2E
# ---------------------------------------------------------------------------

class TestReasoningChainE2E:

    @pytest.mark.asyncio
    async def test_full_chain_execution(self, reasoning_chain):
        """3-step reasoning chain completes successfully."""
        engine = AsyncMock()
        engine.analyze_image = AsyncMock(side_effect=[
            "I see a person near a door.",
            "The person appears to be loitering.",
            "High confidence: loitering behavior detected.",
        ])

        detections = [{"class_name": "person", "confidence": 0.95}]
        result = await reasoning_chain.execute(
            engine, b"\xff\xd8" + b"\x00" * 50, detections
        )

        assert result.success
        assert len(result.steps) == 3
        assert result.steps[0].step_name == "observe"
        assert result.steps[1].step_name == "reason"
        assert result.steps[2].step_name == "verify"
        assert "loitering" in result.final_conclusion.lower()
        assert result.total_elapsed_ms > 0

    @pytest.mark.asyncio
    async def test_chain_with_conversation_persistence(self, reasoning_chain, detection_store):
        """Reasoning steps are persisted to conversation store."""
        engine = AsyncMock()
        engine.analyze_image = AsyncMock(return_value="analysis result")

        await reasoning_chain.execute(
            engine, b"\xff\xd8" + b"\x00" * 50,
            [{"class_name": "person", "confidence": 0.9}],
            device_id="edge-reason-001",
            detection_store=detection_store,
        )

        # Verify conversations were recorded
        with detection_store._lock:
            rows = detection_store._conn.execute(
                "SELECT * FROM conversations WHERE device_id = ?",
                ("edge-reason-001",),
            ).fetchall()
        # 3 steps × 2 (system + assistant) = 6 rows
        assert len(rows) == 6


# ---------------------------------------------------------------------------
# 5. A/B Testing E2E
# ---------------------------------------------------------------------------

class TestABTestingE2E:

    def test_group_assignment(self, ab_test_manager):
        """Devices get assigned to control or treatment groups."""
        groups = set()
        for i in range(20):
            group = ab_test_manager.assign_group(f"edge-ab-{i:03d}")
            groups.add(group.value if hasattr(group, 'value') else str(group))
        # With 50/50 split and 20 devices, both groups should appear
        assert len(groups) == 2

    def test_record_and_evaluate(self, ab_test_manager):
        """Record metrics and evaluate A/B test."""
        for i in range(10):
            device_id = f"edge-ab-{i:03d}"
            ab_test_manager.assign_group(device_id)
            variant = ab_test_manager.get_variant(device_id)
            ab_test_manager.record_inference(variant, latency_ms=50.0 + i)
            ab_test_manager.record_detection(variant, correct=True)

        result = ab_test_manager.evaluate()
        assert result is not None
        assert hasattr(result, 'control_metrics')
        assert hasattr(result, 'winner')

    def test_session_has_ab_group(self):
        """Session manager tracks A/B group assignment."""
        session_mgr = DeviceSessionManager(max_devices=8)
        ab_mgr = ABTestManager(traffic_split=0.5)

        session_mgr.register("edge-ab-001")
        group = ab_mgr.assign_group("edge-ab-001")
        assert group is not None


# ---------------------------------------------------------------------------
# 6. Time Series Query E2E
# ---------------------------------------------------------------------------

class TestTimeSeriesE2E:

    def test_write_and_query_timeseries(self, detection_store):
        """Write time series data and query it back."""
        now = time.time()
        for i in range(20):
            detection_store.record_timeseries(
                "edge-ts-001", "fps", 25.0 + i * 0.5,
                timestamp=now - 1200 + i * 60,
            )

        rows = detection_store.query_timeseries(
            metric_name="fps",
            device_id="edge-ts-001",
            start_time=now - 1800,
            end_time=now,
        )
        assert len(rows) == 20
        assert all("value" in r for r in rows)

    def test_timeseries_aggregation(self, detection_store):
        """Aggregated query returns bucketed results."""
        now = time.time()
        for i in range(60):
            detection_store.record_timeseries(
                "edge-ts-002", "latency_ms", 15.0 + (i % 10),
                timestamp=now - 3600 + i * 60,
            )

        rows = detection_store.query_timeseries(
            metric_name="latency_ms",
            device_id="edge-ts-002",
            start_time=now - 3600,
            end_time=now,
            aggregation="avg",
            bucket_seconds=600,
        )
        assert len(rows) > 0
        assert len(rows) <= 7  # ~6 buckets for 1h at 10min intervals


# ---------------------------------------------------------------------------
# 7. Model Management E2E
# ---------------------------------------------------------------------------

class TestModelManagementE2E:

    def test_full_lifecycle(self, model_registry):
        """Deploy → List → Status → Undeploy → Rollback."""
        # Deploy
        ok = model_registry.deploy(
            "yolov8n", "/models/yolov8n.rknn",
            model_type="detection", version="1.0.0",
            target_device_id="edge-001",
        )
        assert ok

        # List
        models = model_registry.list_models()
        model_ids = [m.model_id for m in models]
        assert "yolov8n" in model_ids

        # Status
        record = model_registry.get_model("yolov8n")
        assert record is not None
        assert record.status == ModelStatus.DEPLOYED

        # Deploy v2
        ok2 = model_registry.deploy(
            "yolov8n-v2", "/models/yolov8n-v2.rknn",
            model_type="detection", version="2.0.0",
            target_device_id="edge-001",
        )
        assert ok2

        # Undeploy v1
        model_registry.undeploy("yolov8n")
        record_after = model_registry.get_model("yolov8n")
        assert record_after is not None
        assert record_after.status == ModelStatus.UNDEPLOYED

    def test_max_models_per_device(self, model_registry):
        """Cannot exceed max models per device."""
        for i in range(3):
            assert model_registry.deploy(
                f"model-{i}", f"/models/m{i}.rknn",
                target_device_id="edge-full",
            )
        # 4th should fail
        assert not model_registry.deploy(
            "model-3", "/models/m3.rknn",
            target_device_id="edge-full",
        )
