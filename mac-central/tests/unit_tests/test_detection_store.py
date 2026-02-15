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

    def test_record_with_device_id(self, store):
        now = time.time()
        store.record({"type": "detection", "frame_id": 1, "timestamp": now, "device_id": "edge-001"})
        store.record({"type": "detection", "frame_id": 2, "timestamp": now, "device_id": "edge-002"})
        store.record({"type": "detection", "frame_id": 3, "timestamp": now, "device_id": "edge-001"})
        assert store.count() == 3

    def test_query_filter_by_device_id(self, store):
        now = time.time()
        store.record({"type": "detection", "frame_id": 1, "timestamp": now, "device_id": "edge-001"})
        store.record({"type": "detection", "frame_id": 2, "timestamp": now, "device_id": "edge-002"})
        store.record({"type": "detection", "frame_id": 3, "timestamp": now, "device_id": "edge-001"})

        results = store.query(since=0, device_id="edge-001")
        assert len(results) == 2
        assert all(r["device_id"] == "edge-001" for r in results)

        results_all = store.query(since=0)
        assert len(results_all) == 3

    def test_migration_adds_device_id(self, tmp_path):
        """Legacy DB without device_id column should be migrated."""
        db_path = tmp_path / "legacy.db"
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                frame_id INTEGER,
                trace_id TEXT,
                event_type TEXT NOT NULL,
                detections_json TEXT,
                vlm_result TEXT,
                rule_matched TEXT
            );
        """)
        conn.execute(
            "INSERT INTO detections (timestamp, frame_id, event_type) VALUES (?, ?, ?)",
            (time.time(), 1, "detection"),
        )
        conn.commit()
        conn.close()

        # Open with new DetectionStore — should migrate
        s = DetectionStore(db_path)
        assert s.count() == 1
        results = s.query(since=0)
        assert results[0]["device_id"] == ""
        # New records should work with device_id
        s.record({"type": "detection", "frame_id": 2, "timestamp": time.time(), "device_id": "edge-001"})
        results = s.query(since=0, device_id="edge-001")
        assert len(results) == 1
        s.close()
