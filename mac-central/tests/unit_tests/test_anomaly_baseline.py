"""Tests for anomaly baseline learning and detection."""

import time
import math
import pytest
from pathlib import Path

from src.application_logic.anomaly_baseline import (
    AnomalyBaseline, BaselineStats, AnomalyScore,
)
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestAnomalyBaseline:
    def test_no_store_returns_none(self):
        ab = AnomalyBaseline(detection_store=None)
        result = ab.learn_baseline("edge-001", "detections_count")
        assert result is None

    def test_insufficient_samples(self, store):
        now = time.time()
        for i in range(5):
            store.record_timeseries("edge-001", "detections_count", 3.0, now - i * 60)

        ab = AnomalyBaseline(detection_store=store, min_samples=50)
        result = ab.learn_baseline("edge-001", "detections_count")
        assert result is None

    def test_learn_baseline(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries(
                "edge-001", "detections_count", 10.0 + (i % 3), now - i * 60
            )

        ab = AnomalyBaseline(
            detection_store=store, min_samples=50, baseline_window_hours=24.0
        )
        baseline = ab.learn_baseline("edge-001", "detections_count")
        assert baseline is not None
        assert baseline.sample_count == 100
        assert 10.0 <= baseline.mean <= 12.0
        assert baseline.std_dev > 0

    def test_score_normal(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", 30.0, now - i * 60)

        ab = AnomalyBaseline(
            detection_store=store, min_samples=50, z_score_threshold=3.0
        )
        ab.learn_baseline("edge-001", "fps")
        score = ab.score("edge-001", "fps", 30.0)
        assert score.is_anomaly is False
        assert score.z_score == 0.0

    def test_score_anomaly(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", 30.0 + (i % 2), now - i * 60)

        ab = AnomalyBaseline(
            detection_store=store, min_samples=50, z_score_threshold=3.0
        )
        ab.learn_baseline("edge-001", "fps")
        # Value far from mean
        score = ab.score("edge-001", "fps", 100.0)
        assert score.is_anomaly is True
        assert score.z_score > 3.0

    def test_score_no_baseline(self):
        ab = AnomalyBaseline(detection_store=None)
        score = ab.score("edge-001", "fps", 30.0)
        assert score.is_anomaly is False
        assert score.z_score == 0.0

    def test_get_baseline(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", 25.0, now - i * 60)

        ab = AnomalyBaseline(detection_store=store, min_samples=50)
        ab.learn_baseline("edge-001", "fps")
        baseline = ab.get_baseline("edge-001", "fps")
        assert baseline is not None
        assert baseline.mean == 25.0

    def test_list_baselines(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", 25.0, now - i * 60)
            store.record_timeseries("edge-001", "detections_count", 5.0, now - i * 60)

        ab = AnomalyBaseline(detection_store=store, min_samples=50)
        ab.learn_baseline("edge-001", "fps")
        ab.learn_baseline("edge-001", "detections_count")
        baselines = ab.list_baselines()
        assert len(baselines) == 2

    def test_zero_std_dev(self, store):
        """All identical values → std_dev=0, same value is not anomaly."""
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", 30.0, now - i * 60)

        ab = AnomalyBaseline(detection_store=store, min_samples=50)
        ab.learn_baseline("edge-001", "fps")
        score = ab.score("edge-001", "fps", 30.0)
        assert score.is_anomaly is False

        # Different value with zero std → infinite z-score → anomaly
        score2 = ab.score("edge-001", "fps", 31.0)
        assert score2.is_anomaly is True
