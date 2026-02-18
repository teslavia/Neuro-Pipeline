"""Tests for time-series and conversation storage."""

import time
import pytest
from pathlib import Path
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestTimeSeriesStore:
    def test_record_and_query_raw(self, store):
        now = time.time()
        store.record_timeseries("edge-001", "fps", 30.0, now - 10)
        store.record_timeseries("edge-001", "fps", 25.0, now - 5)
        store.record_timeseries("edge-001", "fps", 28.0, now)

        rows = store.query_timeseries("fps", device_id="edge-001",
                                       start_time=now - 20, end_time=now + 1)
        assert len(rows) == 3
        assert rows[0]["value"] == 30.0
        assert rows[2]["value"] == 28.0

    def test_query_with_aggregation(self, store):
        now = time.time()
        # Insert 6 points across 2 buckets (bucket_seconds=10)
        for i in range(3):
            store.record_timeseries("edge-001", "detections_count", float(i + 1), now - 15 + i)
        for i in range(3):
            store.record_timeseries("edge-001", "detections_count", float(i + 4), now - 5 + i)

        rows = store.query_timeseries(
            "detections_count", device_id="edge-001",
            start_time=now - 20, end_time=now + 1,
            aggregation="avg", bucket_seconds=10,
        )
        assert len(rows) >= 1  # at least one bucket

    def test_query_sum_aggregation(self, store):
        now = time.time()
        # Align to 60-second bucket to avoid cross-boundary issues
        base = int(now // 60) * 60 + 30  # Middle of a bucket
        store.record_timeseries("edge-001", "count", 1.0, base - 5)
        store.record_timeseries("edge-001", "count", 2.0, base - 4)
        store.record_timeseries("edge-001", "count", 3.0, base - 3)

        rows = store.query_timeseries(
            "count", device_id="edge-001",
            start_time=base - 10, end_time=base + 10,
            aggregation="sum", bucket_seconds=60,
        )
        assert len(rows) == 1
        assert rows[0]["value"] == 6.0

    def test_query_filters_by_device(self, store):
        now = time.time()
        store.record_timeseries("edge-001", "fps", 30.0, now)
        store.record_timeseries("edge-002", "fps", 20.0, now)

        rows = store.query_timeseries("fps", device_id="edge-001",
                                       start_time=now - 1, end_time=now + 1)
        assert len(rows) == 1
        assert rows[0]["value"] == 30.0

    def test_query_filters_by_metric(self, store):
        now = time.time()
        store.record_timeseries("edge-001", "fps", 30.0, now)
        store.record_timeseries("edge-001", "latency", 5.0, now)

        rows = store.query_timeseries("latency", device_id="edge-001",
                                       start_time=now - 1, end_time=now + 1)
        assert len(rows) == 1
        assert rows[0]["value"] == 5.0

    def test_default_time_range(self, store):
        now = time.time()
        store.record_timeseries("edge-001", "fps", 30.0, now)
        # Query with defaults (last 24h)
        rows = store.query_timeseries("fps", device_id="edge-001")
        assert len(rows) == 1


class TestConversationStore:
    def test_record_and_query(self, store):
        now = time.time()
        store.record_conversation("edge-001", "user", "What do you see?", timestamp=now - 2)
        store.record_conversation("edge-001", "assistant", "A person walking.", timestamp=now - 1)
        store.record_conversation("edge-001", "user", "Is it suspicious?", timestamp=now)

        convs = store.query_conversations("edge-001")
        assert len(convs) == 3
        assert convs[0]["role"] == "user"
        assert convs[1]["role"] == "assistant"
        assert convs[2]["content"] == "Is it suspicious?"

    def test_filter_by_context_type(self, store):
        now = time.time()
        store.record_conversation("edge-001", "user", "VLM query", context_type="vlm", timestamp=now)
        store.record_conversation("edge-001", "system", "Reasoning step", context_type="reasoning", timestamp=now)

        vlm = store.query_conversations("edge-001", context_type="vlm")
        assert len(vlm) == 1
        assert vlm[0]["context_type"] == "vlm"

    def test_filter_by_since(self, store):
        now = time.time()
        store.record_conversation("edge-001", "user", "old", timestamp=now - 100)
        store.record_conversation("edge-001", "user", "new", timestamp=now)

        convs = store.query_conversations("edge-001", since=now - 10)
        assert len(convs) == 1
        assert convs[0]["content"] == "new"

    def test_limit(self, store):
        now = time.time()
        for i in range(10):
            store.record_conversation("edge-001", "user", f"msg-{i}", timestamp=now + i)

        convs = store.query_conversations("edge-001", limit=3)
        assert len(convs) == 3

    def test_device_isolation(self, store):
        now = time.time()
        store.record_conversation("edge-001", "user", "hello", timestamp=now)
        store.record_conversation("edge-002", "user", "world", timestamp=now)

        convs = store.query_conversations("edge-001")
        assert len(convs) == 1
        assert convs[0]["content"] == "hello"
