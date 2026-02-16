"""Tests for time series analysis engine."""

import time
import pytest
from pathlib import Path

from src.analytics.timeseries_engine import TimeSeriesEngine, TrendResult
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestTimeSeriesEngine:
    def test_no_store(self):
        engine = TimeSeriesEngine(detection_store=None)
        result = engine.detect_trend("edge-001", "fps")
        assert result is None

    def test_insufficient_data(self, store):
        now = time.time()
        store.record_timeseries("edge-001", "fps", 30.0, now)
        engine = TimeSeriesEngine(detection_store=store)
        result = engine.detect_trend("edge-001", "fps")
        assert result is None

    def test_increasing_trend(self, store):
        now = time.time()
        for i in range(50):
            store.record_timeseries("edge-001", "fps", 10.0 + i * 0.5, now - 3000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        result = engine.detect_trend("edge-001", "fps", hours=2.0)
        assert result is not None
        assert result.direction == "increasing"
        assert result.slope > 0

    def test_decreasing_trend(self, store):
        now = time.time()
        for i in range(50):
            store.record_timeseries("edge-001", "fps", 30.0 - i * 0.5, now - 3000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        result = engine.detect_trend("edge-001", "fps", hours=2.0)
        assert result is not None
        assert result.direction == "decreasing"
        assert result.slope < 0

    def test_stable_trend(self, store):
        now = time.time()
        for i in range(50):
            store.record_timeseries("edge-001", "fps", 30.0, now - 3000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        result = engine.detect_trend("edge-001", "fps", hours=2.0)
        assert result is not None
        assert result.direction == "stable"

    def test_anomaly_points(self, store):
        now = time.time()
        for i in range(100):
            val = 30.0 if i != 50 else 100.0  # spike at i=50
            store.record_timeseries("edge-001", "fps", val, now - 6000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        anomalies = engine.detect_anomaly_points("edge-001", "fps", hours=3.0)
        assert len(anomalies) >= 1
        assert any(a.value == 100.0 for a in anomalies)

    def test_no_anomalies_uniform(self, store):
        now = time.time()
        for i in range(50):
            store.record_timeseries("edge-001", "fps", 30.0, now - 3000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        anomalies = engine.detect_anomaly_points("edge-001", "fps", hours=2.0)
        assert len(anomalies) == 0

    def test_compute_statistics(self, store):
        now = time.time()
        for i in range(100):
            store.record_timeseries("edge-001", "fps", float(i), now - 6000 + i * 60)

        engine = TimeSeriesEngine(detection_store=store)
        stats = engine.compute_statistics("edge-001", "fps", hours=3.0)
        assert stats is not None
        assert stats["count"] == 100
        assert stats["min"] == 0.0
        assert stats["max"] == 99.0
        assert 49.0 <= stats["mean"] <= 50.0

    def test_statistics_no_data(self, store):
        engine = TimeSeriesEngine(detection_store=store)
        stats = engine.compute_statistics("edge-001", "nonexistent", hours=1.0)
        assert stats is None
