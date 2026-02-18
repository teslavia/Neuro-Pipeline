"""Tests for RAG history retriever."""

import time
import pytest
from pathlib import Path

from src.inference.rag_retriever import RAGRetriever, RAGContext
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestRAGRetriever:
    def test_no_store_returns_empty(self):
        retriever = RAGRetriever(detection_store=None)
        ctx = retriever.retrieve("edge-001")
        assert ctx.items == []
        assert "No history" in ctx.summary

    def test_retrieve_from_store(self, store):
        now = time.time()
        for i in range(5):
            store.record({
                "type": "detection",
                "timestamp": now - 3600 + i * 60,
                "frame_id": i,
                "device_id": "edge-001",
                "detections": [{"class_name": "person", "confidence": 0.9}],
            })

        retriever = RAGRetriever(detection_store=store, max_items=10)
        ctx = retriever.retrieve("edge-001")
        assert len(ctx.items) == 5
        assert ctx.query_time_ms >= 0

    def test_filter_by_class_name(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 100,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [{"class_name": "person", "confidence": 0.9}],
        })
        store.record({
            "type": "detection", "timestamp": now - 50,
            "frame_id": 2, "device_id": "edge-001",
            "detections": [{"class_name": "car", "confidence": 0.8}],
        })

        retriever = RAGRetriever(detection_store=store, max_items=10)
        ctx = retriever.retrieve("edge-001", class_names=["person"])
        assert len(ctx.items) == 1
        assert ctx.items[0]["detections"][0]["class_name"] == "person"

    def test_max_items_limit(self, store):
        now = time.time()
        for i in range(20):
            store.record({
                "type": "detection", "timestamp": now - 1000 + i * 10,
                "frame_id": i, "device_id": "edge-001",
                "detections": [{"class_name": "person", "confidence": 0.9}],
            })

        retriever = RAGRetriever(detection_store=store, max_items=5)
        ctx = retriever.retrieve("edge-001")
        assert len(ctx.items) <= 5

    def test_device_isolation(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 100,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [{"class_name": "person", "confidence": 0.9}],
        })
        store.record({
            "type": "detection", "timestamp": now - 50,
            "frame_id": 2, "device_id": "edge-002",
            "detections": [{"class_name": "car", "confidence": 0.8}],
        })

        retriever = RAGRetriever(detection_store=store, max_items=10)
        ctx = retriever.retrieve("edge-001")
        assert len(ctx.items) == 1

    def test_summary_format(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 100,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [{"class_name": "person", "confidence": 0.9}],
        })

        retriever = RAGRetriever(detection_store=store)
        ctx = retriever.retrieve("edge-001")
        assert "edge-001" in ctx.summary
        assert "person" in ctx.summary

    def test_format_for_prompt(self, store):
        retriever = RAGRetriever(detection_store=store)
        ctx = RAGContext(items=[], summary="Test summary", query_time_ms=1.0)
        result = retriever.format_for_prompt(ctx)
        assert result == "Test summary"

    def test_time_window_override(self, store):
        now = time.time()
        # Event 2 hours ago
        store.record({
            "type": "detection", "timestamp": now - 7200,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [{"class_name": "person", "confidence": 0.9}],
        })

        retriever = RAGRetriever(detection_store=store, time_window_hours=1.0)
        ctx = retriever.retrieve("edge-001")
        assert len(ctx.items) == 0

        ctx2 = retriever.retrieve("edge-001", time_window_hours=3.0)
        assert len(ctx2.items) == 1
