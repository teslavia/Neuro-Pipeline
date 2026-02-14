"""Unit tests for DetectionStore."""

import time
import pytest
from pathlib import Path

from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    s = DetectionStore(tmp_path / "test.db", retention_days=1)
    yield s
    s.close()


class TestDetectionStore:
    def test_record_and_count(self, store):
        store.record({"type": "detection", "frame_id": 1, "timestamp": time.time()})
        store.record({"type": "detection", "frame_id": 2, "timestamp": time.time()})
        assert store.count() == 2

    def test_query_time_range(self, store):
        now = time.time()
        store.record({"type": "detection", "frame_id": 1, "timestamp": now - 3600})
        store.record({"type": "detection", "frame_id": 2, "timestamp": now - 60})
        store.record({"type": "detection", "frame_id": 3, "timestamp": now})

        # Query last 30 minutes
        results = store.query(since=now - 1800)
        assert len(results) == 2
        assert results[0]["frame_id"] == 3  # DESC order

    def test_query_with_limit(self, store):
        now = time.time()
        for i in range(10):
            store.record({"type": "detection", "frame_id": i, "timestamp": now})
        results = store.query(since=now - 1, limit=3)
        assert len(results) == 3

    def test_record_vlm_event(self, store):
        store.record({
            "type": "vlm_analysis",
            "frame_id": 42,
            "trace_id": "edge-42",
            "detections": [{"class_name": "person", "confidence": 0.95}],
            "vlm_result": "Person walking near entrance",
            "rule": "person",
            "timestamp": time.time(),
        })
        results = store.query(since=0)
        assert len(results) == 1
        assert results[0]["event_type"] == "vlm_analysis"
        assert results[0]["vlm_result"] == "Person walking near entrance"
        assert results[0]["detections"][0]["class_name"] == "person"

    def test_cleanup_old_events(self, store):
        now = time.time()
        store.record({"type": "detection", "frame_id": 1, "timestamp": now - 200000})
        store.record({"type": "detection", "frame_id": 2, "timestamp": now})
        deleted = store.cleanup()
        assert deleted == 1
        assert store.count() == 1

    def test_close_and_reopen(self, tmp_path):
        db_path = tmp_path / "persist.db"
        s1 = DetectionStore(db_path)
        s1.record({"type": "detection", "frame_id": 1, "timestamp": time.time()})
        s1.close()

        s2 = DetectionStore(db_path)
        assert s2.count() == 1
        s2.close()
