"""End-to-end integration test: gRPC → Orchestrator → SQLite → Dashboard."""

import asyncio
import time

import grpc
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc
from src.communication.grpc_server import NeuroPipelineServer
from src.application_logic.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from src.storage.detection_store import DetectionStore


@pytest_asyncio.fixture
async def e2e_stack(tmp_path):
    """Full stack: gRPC server + orchestrator + SQLite store."""
    db_path = tmp_path / "e2e_test.db"
    store = DetectionStore(db_path)

    orch = CentralOrchestrator(
        model_path=Path("models/test"),
        vlm_rules=[VLMTriggerRule("person", 0.8, "person_behavior")],
        detection_store=store,
    )
    orch._batch_max_size = 1
    orch._batch_timeout = 0.05
    # Mock inference engine (no real model needed)
    orch.inference_engine = MagicMock()
    orch.inference_engine.load_model = AsyncMock()
    orch.inference_engine.unload_model = AsyncMock()
    orch.inference_engine.analyze_image = AsyncMock(
        return_value="Person detected near entrance, walking normally."
    )
    orch._vlm_worker_task = asyncio.create_task(orch._vlm_worker())

    srv = NeuroPipelineServer("localhost", 50299, orch)
    await srv.start()

    channel = grpc.aio.insecure_channel("localhost:50299")
    yield {
        "server": srv,
        "channel": channel,
        "orchestrator": orch,
        "store": store,
        "db_path": db_path,
    }

    await channel.close()
    await srv.stop(grace=0.1)
    if orch._vlm_worker_task:
        orch._vlm_worker_task.cancel()
        try:
            await orch._vlm_worker_task
        except asyncio.CancelledError:
            pass
    store.close()


@pytest.mark.asyncio
async def test_e2e_detection_to_sqlite(e2e_stack):
    """Detection stream → orchestrator → SQLite persistence."""
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(e2e_stack["channel"])

    async def send_detections():
        for i in range(5):
            result = neuro_pipeline_pb2.DetectionResult()
            result.frame_id = i + 1
            result.device_id = "edge-e2e"
            result.trace_id = f"e2e-{i}"
            box = result.boxes.add()
            box.class_name = "car"
            box.confidence = 0.7
            box.x_min, box.y_min = 0.1, 0.2
            box.x_max, box.y_max = 0.5, 0.6
            yield result

    resp = await stub.StreamDetectionResults(send_detections())
    assert resp.success is True
    assert resp.frames_received == 5

    # Verify events persisted in SQLite
    store = e2e_stack["store"]
    assert store.count() == 5
    events = store.query(since=0)
    assert all(e["event_type"] == "detection" for e in events)


@pytest.mark.asyncio
async def test_e2e_vlm_trigger_and_persist(e2e_stack):
    """High-confidence person → VLM queue → vlm_analysis event in SQLite."""
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(e2e_stack["channel"])

    async def send_person_detection():
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = 100
        result.device_id = "edge-e2e"
        result.trace_id = "vlm-trigger"
        result.frame_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50  # fake JPEG
        box = result.boxes.add()
        box.class_name = "person"
        box.confidence = 0.95  # above 0.8 threshold
        box.x_min, box.y_min = 0.2, 0.3
        box.x_max, box.y_max = 0.8, 0.9
        yield result

    resp = await stub.StreamDetectionResults(send_person_detection())
    assert resp.success is True

    # Wait for VLM worker to process the queue
    await asyncio.sleep(0.5)

    store = e2e_stack["store"]
    events = store.query(since=0)
    types = [e["event_type"] for e in events]
    assert "detection" in types
    assert "vlm_analysis" in types

    vlm_events = [e for e in events if e["event_type"] == "vlm_analysis"]
    assert len(vlm_events) == 1
    assert "Person detected" in vlm_events[0]["vlm_result"]


@pytest.mark.asyncio
async def test_e2e_recent_events_in_memory(e2e_stack):
    """Orchestrator maintains in-memory recent events."""
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(e2e_stack["channel"])

    async def send_one():
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = 200
        result.device_id = "edge-e2e"
        result.trace_id = "mem-test"
        yield result

    await stub.StreamDetectionResults(send_one())

    orch = e2e_stack["orchestrator"]
    recent = orch.get_recent_events(limit=10)
    assert len(recent) >= 1
    assert any(e.get("frame_id") == 200 for e in recent)


@pytest.mark.asyncio
async def test_e2e_dashboard_reads_sqlite(e2e_stack):
    """Dashboard /api/events/history returns data from the same SQLite store."""
    from extensions.dashboard.app import app
    from extensions.dashboard.services import set_detection_store

    store = e2e_stack["store"]
    # Insert directly to ensure data exists
    store.record({
        "type": "detection",
        "frame_id": 999,
        "trace_id": "dash-test",
        "timestamp": time.time(),
        "detections": [{"class_name": "person", "confidence": 0.9}],
    })
    set_detection_store(store)

    try:
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/events/history", params={"hours": 1})
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] >= 1
            frame_ids = [e["frame_id"] for e in data["events"]]
            assert 999 in frame_ids
    finally:
        set_detection_store(None)
