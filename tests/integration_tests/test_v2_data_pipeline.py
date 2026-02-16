"""
Data pipeline verification tests: ReportGenerator, TimeSeriesEngine,
AutoAnnotator, ReIDEngine.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central"))

from src.reporting.report_generator import ReportGenerator
from src.analytics.timeseries_engine import TimeSeriesEngine
from src.analytics.auto_annotator import AutoAnnotator
from src.analytics.reid_engine import ReIDEngine
from src.storage.detection_store import DetectionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detection_store(tmp_path):
    store = DetectionStore(tmp_path / "data_pipeline.db")
    yield store
    store.close()


@pytest.fixture
def populated_store(detection_store):
    """Store with mixed event types for report generation."""
    now = time.time()
    # Detection events
    for i in range(10):
        detection_store.record({
            "type": "detection",
            "frame_id": i,
            "trace_id": f"t-{i}",
            "timestamp": now - 600 + i * 60,
            "detections": [
                {"class_name": "person", "confidence": 0.9},
                {"class_name": "car", "confidence": 0.85},
            ],
            "device_id": "edge-rpt-001",
        })
    # VLM analysis events
    for i in range(3):
        detection_store.record({
            "type": "vlm_analysis",
            "frame_id": 100 + i,
            "trace_id": f"vlm-{i}",
            "timestamp": now - 300 + i * 60,
            "detections": [{"class_name": "person", "confidence": 0.95}],
            "vlm_result": f"Person near entrance, analysis #{i}",
            "device_id": "edge-rpt-001",
        })
    # Behavior alerts
    for i in range(2):
        detection_store.record({
            "type": "behavior_alert",
            "frame_id": 200 + i,
            "trace_id": f"beh-{i}",
            "timestamp": now - 120 + i * 60,
            "detections": [],
            "device_id": "edge-rpt-001",
        })
    return detection_store


# ---------------------------------------------------------------------------
# 1. ReportGenerator
# ---------------------------------------------------------------------------

class TestReportGenerator:

    def test_generate_report(self, populated_store):
        """Generate report from mixed events."""
        gen = ReportGenerator(detection_store=populated_store)
        report = gen.generate(
            device_id="edge-rpt-001",
            time_range_hours=1.0,
        )
        assert report is not None
        assert len(report.sections) > 0
        # Should have detection summary section
        section_names = [s.title for s in report.sections]
        assert any("detection" in t.lower() or "summary" in t.lower() for t in section_names)

    def test_report_empty_device(self, detection_store):
        """Report for device with no events."""
        gen = ReportGenerator(detection_store=detection_store)
        report = gen.generate(device_id="edge-empty", time_range_hours=1.0)
        assert report is not None
        # Should still produce a report, just with empty/minimal sections


# ---------------------------------------------------------------------------
# 2. TimeSeriesEngine
# ---------------------------------------------------------------------------

class TestTimeSeriesEngine:

    def test_detect_upward_trend(self, detection_store):
        """Detect upward trend in increasing data."""
        engine = TimeSeriesEngine(detection_store=detection_store)
        now = time.time()
        # Linearly increasing data
        for i in range(50):
            detection_store.record_timeseries(
                "edge-trend-001", "fps",
                10.0 + i * 2.0,
                timestamp=now - 3600 + i * 60,
            )
        result = engine.detect_trend("edge-trend-001", "fps", hours=2.0)
        assert result is not None
        assert result.direction == "increasing"
        assert result.slope > 0

    def test_detect_downward_trend(self, detection_store):
        """Detect downward trend in decreasing data."""
        engine = TimeSeriesEngine(detection_store=detection_store)
        now = time.time()
        for i in range(50):
            detection_store.record_timeseries(
                "edge-trend-002", "latency",
                100.0 - i * 1.5,
                timestamp=now - 3600 + i * 60,
            )
        result = engine.detect_trend("edge-trend-002", "latency", hours=2.0)
        assert result is not None
        assert result.direction == "decreasing"
        assert result.slope < 0

    def test_detect_anomaly_points(self, detection_store):
        """Detect anomaly points in data with outliers."""
        engine = TimeSeriesEngine(detection_store=detection_store)
        now = time.time()
        for i in range(50):
            val = 10.0
            if i == 25:
                val = 100.0  # outlier
            if i == 40:
                val = -50.0  # outlier
            detection_store.record_timeseries(
                "edge-anom-pts", "metric_x", val,
                timestamp=now - 3600 + i * 60,
            )

        anomalies = engine.detect_anomaly_points("edge-anom-pts", "metric_x", hours=2.0)
        assert len(anomalies) >= 2

    def test_compute_statistics(self, detection_store):
        """Compute basic statistics on data."""
        engine = TimeSeriesEngine(detection_store=detection_store)
        now = time.time()
        for i in range(100):
            detection_store.record_timeseries(
                "edge-stats", "inference_ms", float(i),
                timestamp=now - 7200 + i * 60,
            )
        stats = engine.compute_statistics("edge-stats", "inference_ms", hours=3.0)
        assert stats is not None
        assert "mean" in stats
        assert stats["count"] == 100


# ---------------------------------------------------------------------------
# 3. AutoAnnotator
# ---------------------------------------------------------------------------

class TestAutoAnnotator:

    def test_collect_and_export_coco(self, populated_store):
        """Collect high-confidence samples and export COCO format."""
        annotator = AutoAnnotator(
            detection_store=populated_store,
            min_confidence=0.8,
        )
        samples = annotator.collect_samples(
            device_id="edge-rpt-001",
            hours=1.0,
        )
        assert len(samples) > 0

        coco = annotator.export_coco(samples)
        assert "images" in coco
        assert "annotations" in coco
        assert "categories" in coco
        assert len(coco["images"]) > 0

    def test_export_yolo(self, populated_store):
        """Export in YOLO format."""
        annotator = AutoAnnotator(
            detection_store=populated_store,
            min_confidence=0.8,
        )
        samples = annotator.collect_samples(
            device_id="edge-rpt-001",
            hours=1.0,
        )

        yolo_lines = annotator.export_yolo(samples)
        assert isinstance(yolo_lines, list)
        assert len(yolo_lines) > 0


# ---------------------------------------------------------------------------
# 4. ReIDEngine
# ---------------------------------------------------------------------------

class TestReIDEngine:

    def test_register_and_match(self):
        """Register features and find cross-device matches."""
        reid = ReIDEngine(similarity_threshold=0.9)

        feature_a = [0.5] * 128
        reid.register_feature("edge-001", "person", feature_a)

        # Very similar feature from different device
        feature_b = [0.5 + 0.0001 * i for i in range(128)]
        matches = reid.find_matches(feature_b, class_name="person", exclude_device="edge-002")
        assert len(matches) >= 1
        assert matches[0].target_device_id == "edge-001"

    def test_get_track(self):
        """Retrieve track by ID after registration."""
        reid = ReIDEngine()
        track_id = reid.register_feature("edge-001", "person", [1.0] * 128)
        assert track_id is not None
        track = reid.get_track(track_id)
        assert track is not None
        assert track.track_id == track_id

    def test_cross_device_creates_shared_track(self):
        """Features from different devices create a shared track with multiple sightings."""
        reid = ReIDEngine(similarity_threshold=0.9)
        feature = [0.5] * 128
        tid1 = reid.register_feature("edge-001", "person", feature)
        tid2 = reid.register_feature("edge-002", "person", feature)
        # Should match to same track
        assert tid1 == tid2
        track = reid.get_track(tid1)
        assert len(track.sightings) == 2

        # list_tracks with min_sightings=2 should include this track
        tracks = reid.list_tracks(min_sightings=2)
        assert len(tracks) == 1

    def test_no_match_different_class(self):
        """Features of different classes should not match."""
        reid = ReIDEngine(similarity_threshold=0.9)
        feature = [0.5] * 128
        reid.register_feature("edge-001", "person", feature)
        matches = reid.find_matches(feature, class_name="car", exclude_device="edge-002")
        assert len(matches) == 0
