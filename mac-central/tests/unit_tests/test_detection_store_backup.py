"""Tests for DetectionStore backup functionality."""

import sqlite3
import time

import pytest

from src.storage.detection_store import DetectionStore


class TestDetectionStoreBackup:
    def test_backup_creates_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = DetectionStore(db_path)
        store.record({"type": "detection", "timestamp": time.time(), "frame_id": 1})

        backup_path = tmp_path / "backups" / "test-backup.db"
        assert store.backup(backup_path)
        assert backup_path.exists()
        store.close()

    def test_backup_contains_data(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = DetectionStore(db_path)
        for i in range(5):
            store.record({"type": "detection", "timestamp": time.time(), "frame_id": i})

        backup_path = tmp_path / "backup.db"
        store.backup(backup_path)

        # Verify backup has the data
        conn = sqlite3.connect(str(backup_path))
        count = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        conn.close()
        assert count == 5
        store.close()

    def test_backup_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = DetectionStore(db_path)
        store.record({"type": "detection", "timestamp": time.time()})

        backup_path = tmp_path / "deep" / "nested" / "backup.db"
        assert store.backup(backup_path)
        assert backup_path.exists()
        store.close()

    def test_backup_after_close_fails(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = DetectionStore(db_path)
        store.record({"type": "detection", "timestamp": time.time()})
        store.close()
        assert not store.backup(tmp_path / "backup.db")

    def test_multiple_backups(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = DetectionStore(db_path)
        store.record({"type": "detection", "timestamp": time.time(), "frame_id": 1})

        for i in range(3):
            backup_path = tmp_path / f"backup-{i}.db"
            assert store.backup(backup_path)
        store.close()
