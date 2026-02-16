"""Tests for central-side behavior analyzer."""

import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.application_logic.behavior_analyzer import (
    BehaviorAnalyzer, BehaviorType, BehaviorEvent,
)
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestBehaviorAnalyzer:
    def test_no_detections_no_events(self):
        analyzer = BehaviorAnalyzer()
        events = analyzer.analyze("edge-001", [])
        assert events == []

    def test_crowd_detection(self):
        analyzer = BehaviorAnalyzer(crowd_threshold=3)
        detections = [
            {"class_name": "person", "confidence": 0.9} for _ in range(5)
        ]
        events = analyzer.analyze("edge-001", detections)
        assert len(events) == 1
        assert events[0].behavior_type == BehaviorType.CROWD
        assert events[0].device_id == "edge-001"
        assert "5 person" in events[0].description

    def test_crowd_below_threshold(self):
        analyzer = BehaviorAnalyzer(crowd_threshold=5)
        detections = [
            {"class_name": "person", "confidence": 0.9} for _ in range(3)
        ]
        events = analyzer.analyze("edge-001", detections)
        assert len(events) == 0

    def test_crowd_per_class(self):
        analyzer = BehaviorAnalyzer(crowd_threshold=3)
        detections = [
            {"class_name": "person", "confidence": 0.9},
            {"class_name": "person", "confidence": 0.8},
            {"class_name": "car", "confidence": 0.9},
            {"class_name": "car", "confidence": 0.8},
        ]
        events = analyzer.analyze("edge-001", detections)
        # Neither class reaches threshold of 3
        assert len(events) == 0

    def test_loitering_detection(self, store):
        analyzer = BehaviorAnalyzer(
            detection_store=store,
            loiter_threshold_seconds=50.0,
            analysis_window_seconds=300.0,
        )
        now = time.time()

        # Simulate person detected across many time buckets
        for i in range(15):
            store.record({
                "type": "detection",
                "timestamp": now - 140 + (i * 10),
                "frame_id": i,
                "device_id": "edge-001",
                "detections": [{"class_name": "person", "confidence": 0.9}],
            })

        current = [{"class_name": "person", "confidence": 0.9}]
        events = analyzer.analyze("edge-001", current, timestamp=now)

        loiter_events = [e for e in events if e.behavior_type == BehaviorType.LOITERING]
        assert len(loiter_events) == 1
        assert "Person detected" in loiter_events[0].description

    def test_no_loitering_without_history(self):
        analyzer = BehaviorAnalyzer(
            detection_store=None,
            loiter_threshold_seconds=60.0,
        )
        current = [{"class_name": "person", "confidence": 0.9}]
        events = analyzer.analyze("edge-001", current)
        loiter_events = [e for e in events if e.behavior_type == BehaviorType.LOITERING]
        assert len(loiter_events) == 0

    def test_confidence_bounded(self):
        analyzer = BehaviorAnalyzer(crowd_threshold=2)
        detections = [
            {"class_name": "person", "confidence": 0.9} for _ in range(100)
        ]
        events = analyzer.analyze("edge-001", detections)
        assert len(events) == 1
        assert 0.0 <= events[0].confidence <= 1.0
