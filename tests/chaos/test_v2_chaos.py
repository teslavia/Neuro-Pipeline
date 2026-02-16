"""
Chaos tests for v2 fault scenarios: RAG failure, anomaly edge cases,
reasoning chain timeout, A/B concurrency, ReID memory.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central"))

from src.application_logic.anomaly_baseline import AnomalyBaseline
from src.llm_vlm.rag_retriever import RAGRetriever
from src.llm_vlm.reasoning_chain import ReasoningChain
from src.model_management.ab_test_manager import ABTestManager
from src.analytics.reid_engine import ReIDEngine
from src.storage.detection_store import DetectionStore


# ---------------------------------------------------------------------------
# 1. RAG Retrieval Failure — graceful degradation
# ---------------------------------------------------------------------------

class TestRAGRetrievalFailure:

    def test_rag_survives_store_exception(self):
        """RAG retriever propagates store exception (no silent swallow)."""
        broken_store = MagicMock()
        broken_store.query = MagicMock(side_effect=RuntimeError("DB corrupted"))

        retriever = RAGRetriever(detection_store=broken_store, max_items=5)
        # RAG retriever does not catch store exceptions — they propagate.
        # The orchestrator's try/except handles this at a higher level.
        with pytest.raises(RuntimeError, match="DB corrupted"):
            retriever.retrieve("edge-001")

    def test_rag_with_none_store(self):
        """RAG retriever with no store returns empty context."""
        retriever = RAGRetriever(detection_store=None)
        ctx = retriever.retrieve("edge-001")
        assert len(ctx.items) == 0
        assert "No history" in ctx.summary

    def test_rag_with_empty_results(self, tmp_path):
        """RAG retriever with store that returns no rows."""
        store = DetectionStore(tmp_path / "empty.db")
        retriever = RAGRetriever(detection_store=store, max_items=5)
        ctx = retriever.retrieve("edge-nonexistent")
        assert len(ctx.items) == 0
        store.close()


# ---------------------------------------------------------------------------
# 2. Anomaly Baseline — no data edge case
# ---------------------------------------------------------------------------

class TestAnomalyBaselineNoData:

    def test_no_false_positive_without_data(self):
        """Anomaly scorer does not fire when no baseline exists."""
        baseline = AnomalyBaseline(
            detection_store=None,
            z_score_threshold=2.0,
            min_samples=10,
        )
        score = baseline.score("edge-001", "fps", 100.0)
        assert not score.is_anomaly
        assert score.z_score == 0.0

    def test_insufficient_samples_no_baseline(self, tmp_path):
        """With fewer samples than min_samples, no baseline is learned."""
        store = DetectionStore(tmp_path / "few.db")
        baseline = AnomalyBaseline(
            detection_store=store,
            min_samples=100,
        )
        # Write only 5 data points
        now = time.time()
        for i in range(5):
            store.record_timeseries("edge-001", "fps", 25.0, timestamp=now - i * 60)

        result = baseline.learn_baseline("edge-001", "fps")
        assert result is None

        # Scoring should still be safe
        score = baseline.score("edge-001", "fps", 999.0)
        assert not score.is_anomaly
        store.close()

    def test_zero_std_dev_baseline(self, tmp_path):
        """Baseline with zero std_dev handles edge case."""
        store = DetectionStore(tmp_path / "zero_std.db")
        baseline = AnomalyBaseline(
            detection_store=store,
            min_samples=10,
            z_score_threshold=2.0,
        )
        now = time.time()
        # All identical values → std_dev = 0
        for i in range(20):
            store.record_timeseries("edge-001", "constant", 42.0, timestamp=now - 3600 + i * 60)

        bl = baseline.learn_baseline("edge-001", "constant")
        assert bl is not None
        assert bl.std_dev == 0.0

        # Same value should not be anomaly
        score_same = baseline.score("edge-001", "constant", 42.0)
        assert not score_same.is_anomaly

        # Different value with zero std → inf z-score → anomaly
        score_diff = baseline.score("edge-001", "constant", 43.0)
        assert score_diff.is_anomaly
        store.close()


# ---------------------------------------------------------------------------
# 3. Reasoning Chain Timeout
# ---------------------------------------------------------------------------

class TestReasoningChainTimeout:

    @pytest.mark.asyncio
    async def test_chain_timeout_does_not_crash(self):
        """Reasoning chain handles step timeout gracefully."""
        chain = ReasoningChain(max_steps=3, timeout_per_step=0.1)

        async def slow_analyze(*args, **kwargs):
            await asyncio.sleep(5.0)
            return "should not reach"

        engine = AsyncMock()
        engine.analyze_image = slow_analyze

        result = await chain.execute(
            engine, b"\xff\xd8" + b"\x00" * 50,
            [{"class_name": "person", "confidence": 0.9}],
        )

        assert not result.success
        assert len(result.steps) >= 1
        assert "timeout" in result.steps[0].result.lower()

    @pytest.mark.asyncio
    async def test_chain_error_does_not_crash(self):
        """Reasoning chain handles engine error gracefully."""
        chain = ReasoningChain(max_steps=3, timeout_per_step=5.0)

        engine = AsyncMock()
        engine.analyze_image = AsyncMock(side_effect=RuntimeError("GPU OOM"))

        result = await chain.execute(
            engine, b"\xff\xd8" + b"\x00" * 50,
            [{"class_name": "person", "confidence": 0.9}],
        )

        assert not result.success
        assert len(result.steps) >= 1
        assert "error" in result.steps[0].result.lower()

    @pytest.mark.asyncio
    async def test_partial_chain_preserves_completed_steps(self):
        """If step 2 fails, step 1 result is still available."""
        chain = ReasoningChain(max_steps=3, timeout_per_step=0.1)

        call_count = 0

        async def flaky_analyze(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "observation complete"
            await asyncio.sleep(5.0)  # timeout on step 2

        engine = AsyncMock()
        engine.analyze_image = flaky_analyze

        result = await chain.execute(
            engine, b"\xff\xd8" + b"\x00" * 50,
            [{"class_name": "person", "confidence": 0.9}],
        )

        assert len(result.steps) == 2
        assert result.steps[0].result == "observation complete"
        assert "timeout" in result.steps[1].result.lower()


# ---------------------------------------------------------------------------
# 4. A/B Manager Concurrency
# ---------------------------------------------------------------------------

class TestABManagerConcurrency:

    def test_concurrent_group_assignment(self):
        """Multiple threads assigning groups simultaneously — no crashes."""
        ab_mgr = ABTestManager(traffic_split=0.5, min_samples=5)
        errors = []

        def assign_batch(start_id, count):
            try:
                for i in range(count):
                    device_id = f"edge-{start_id + i:06d}"
                    ab_mgr.assign_group(device_id)
                    variant = ab_mgr.get_variant(device_id)
                    ab_mgr.record_inference(variant, latency_ms=10.0)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=assign_batch, args=(i * 100, 100))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_evaluate_with_no_data(self):
        """Evaluate with no recorded data does not crash."""
        ab_mgr = ABTestManager(traffic_split=0.5, min_samples=5)
        result = ab_mgr.evaluate()
        # Should return some result (possibly inconclusive) without error
        assert result is not None


# ---------------------------------------------------------------------------
# 5. ReID Engine — large feature set + time window pruning
# ---------------------------------------------------------------------------

class TestReIDLargeScale:

    def test_register_many_features(self):
        """Register 1000 feature vectors without memory issues."""
        reid = ReIDEngine(time_window_seconds=600.0)
        for i in range(1000):
            feature = [float(i % 128) / 128.0] * 128
            reid.register_feature(
                device_id=f"edge-{i % 5:03d}",
                class_name="person",
                feature_vector=feature,
            )

        # Each unique feature from a unique device creates a track
        # list_tracks with min_sightings=1 would return all
        track = reid.get_track("track-0001")
        assert track is not None

    def test_cross_device_matching(self):
        """Similar features from different devices match."""
        reid = ReIDEngine(similarity_threshold=0.9)

        base_feature = [0.5] * 128
        reid.register_feature("edge-001", "person", base_feature)

        # Slightly different feature from another device
        similar_feature = [0.5 + 0.001 * (i % 3) for i in range(128)]
        matches = reid.find_matches(similar_feature, class_name="person", exclude_device="edge-002")

        assert len(matches) >= 1
        assert matches[0].target_device_id == "edge-001"

    def test_dissimilar_features_no_match(self):
        """Very different features do not match."""
        reid = ReIDEngine(similarity_threshold=0.9)

        reid.register_feature("edge-001", "person", [1.0] * 128)
        matches = reid.find_matches([0.0] * 128, class_name="person", exclude_device="edge-002")
        assert len(matches) == 0
