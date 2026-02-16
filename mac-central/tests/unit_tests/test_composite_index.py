"""Tests for composite index on detections table."""

import sqlite3
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from storage.detection_store import DetectionStore


def test_composite_index_exists():
    """The device_id+timestamp composite index should exist after init."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        store = DetectionStore(db_path)
        conn = sqlite3.connect(str(db_path))
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(detections)").fetchall()}
        conn.close()
        store.close()
        assert "idx_detections_device_ts" in indexes


def test_migration_creates_index():
    """Opening a legacy DB should create the composite index."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "legacy.db"
        # Create a minimal legacy DB without the composite index
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
                rule_matched TEXT,
                device_id TEXT DEFAULT ''
            );
            CREATE INDEX idx_detections_ts ON detections(timestamp);
        """)
        conn.close()

        # Open with DetectionStore — should add composite index
        store = DetectionStore(db_path)
        conn = sqlite3.connect(str(db_path))
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(detections)").fetchall()}
        conn.close()
        store.close()
        assert "idx_detections_device_ts" in indexes
