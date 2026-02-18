"""Integration test: SQLite persistence — write/close/reopen/query + cleanup + dashboard API."""

import time
import tempfile

import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import MagicMock

from src.storage.detection_store import DetectionStore


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_detections.db"


@pytest.fixture
def store(db_path):
    s = DetectionStore(db_path, retention_days=7)
    yield s
    s.close()


def _make_event(frame_id: int, ts: float = 0, cls: str = "person") -> dict:
    return {
        "type": "detection",
        "frame_id": frame_id,
        "trace_id": f"trace-{frame_id}",
        "timestamp": ts or time.time(),
        "detections": [{"class_name": cls, "confidence": 0.9}],
    }


class TestPersistenceAcrossRestart:
    """Verify data survives close → reopen cycle."""

    def test_write_close_reopen_query(self, db_path):
        store1 = DetectionStore(db_path)
        store1.record(_make_event(1))
        store1.record(_make_event(2))
        assert store1.count() == 2
        store1.close()

        store2 = DetectionStore(db_path)
        assert store2.count() == 2
        events = store2.query(since=0)
        assert len(events) == 2
        assert events[0]["frame_id"] == 2  # DESC order
        assert events[1]["frame_id"] == 1
        store2.close()

    def test_vlm_event_persists(self, db_path):
        store1 = DetectionStore(db_path)
        store1.record({
            "type": "vlm_analysis",
            "frame_id": 10,
            "trace_id": "vlm-10",
            "timestamp": time.time(),
            "detections": [{"class_name": "person", "confidence": 0.95}],
            "vlm_result": "Person walking near entrance",
            "rule": "person",
        })
        store1.close()

        store2 = DetectionStore(db_path)
        events = store2.query(since=0)
        assert len(events) == 1
        assert events[0]["vlm_result"] == "Person walking near entrance"
        assert events[0]["rule_matched"] == "person"
        store2.close()


class TestCleanup:
    """Verify retention-based cleanup."""

    def test_cleanup_old_events(self, db_path):
        store = DetectionStore(db_path, retention_days=1)
        old_ts = time.time() - 2 * 86400  # 2 days ago
        store.record(_make_event(1, ts=old_ts))
        store.record(_make_event(2, ts=time.time()))
        assert store.count() == 2

        deleted = store.cleanup()
        assert deleted == 1
        assert store.count() == 1
        events = store.query(since=0)
        assert events[0]["frame_id"] == 2
        store.close()

    def test_cleanup_nothing_to_delete(self, store):
        store.record(_make_event(1))
        deleted = store.cleanup()
        assert deleted == 0
        assert store.count() == 1


class TestDashboardHistoryAPI:
    """Verify dashboard /api/events/history reads from SQLite."""

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_sqlite_data(self, db_path):
        from extensions.dashboard.app import app
        from extensions.dashboard.services import set_detection_store

        store = DetectionStore(db_path)
        store.record(_make_event(100, ts=time.time()))
        store.record(_make_event(101, ts=time.time()))
        set_detection_store(store)

        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/events/history", params={"hours": 1})
                assert resp.status_code == 200
                data = resp.json()
                assert data["count"] == 2
                assert len(data["events"]) == 2
        finally:
            set_detection_store(None)
            store.close()

    @pytest.mark.asyncio
    async def test_history_endpoint_no_store(self):
        from extensions.dashboard.app import app
        from extensions.dashboard.services import set_detection_store

        set_detection_store(None)
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/events/history", params={"hours": 1})
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
