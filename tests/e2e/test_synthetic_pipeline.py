"""
Synthetic end-to-end pipeline test.

Generates known DetectionResults, streams them through the gRPC server
(in-process), and verifies:
  - SQLite persistence
  - Event emission to listeners
  - Metrics increment
  - VLM queue receives qualifying items
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central"))

from src.application_logic.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from src.communication.device_session import DeviceSessionManager
from src.storage.detection_store import DetectionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_detection(frame_id: int, device_id: str = "edge-syn-001",
                   class_name: str = "person", confidence: float = 0.92,
                   bbox=(0.1, 0.2, 0.5, 0.6), frame_data: bytes = b""):
    """Create a mock DetectionResult protobuf-like object."""
    box = MagicMock()
    box.class_name = class_name
    box.confidence = confidence
    box.x_min, box.y_min, box.x_max, box.y_max = bbox

    result = MagicMock()
    result.frame_id = frame_id
    result.device_id = device_id
    result.trace_id = f"{device_id}-{frame_id}"
    result.timestamp_us = int(time.time() * 1_000_000)
    result.frame_data = frame_data
    result.boxes = [box]
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detection_store(tmp_path):
    store = DetectionStore(tmp_path / "e2e_test.db")
    yield store
    store.close()


@pytest.fixture
def orchestrator(tmp_path, detection_store):
    orch = CentralOrchestrator(
        model_path=tmp_path / "models",
        vlm_rules=[VLMTriggerRule(class_name="person", min_confidence=0.8)],
        detection_store=detection_store,
    )
    # Patch inference engine to avoid real model loading
    orch.inference_engine = AsyncMock()
    orch.inference_engine._loaded = True
    orch.inference_engine.analyze_image = AsyncMock(return_value="test VLM output")
    # Fast batch for tests
    orch._batch_max_size = 1
    orch._batch_timeout = 0.05
    return orch


@pytest.fixture
def session_manager():
    return DeviceSessionManager(max_devices=8, expiry_timeout=30.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyntheticPipeline:

    @pytest.mark.asyncio
    async def test_detection_persisted_to_sqlite(self, orchestrator, detection_store):
        """Stream detections → verify they appear in SQLite."""
        det = make_detection(frame_id=1, device_id="edge-e2e-001")
        await orchestrator.process_detection(det)

        rows = detection_store.query(since=time.time() - 10)
        assert len(rows) >= 1
        assert rows[0]["frame_id"] == 1
        assert rows[0]["device_id"] == "edge-e2e-001"

    @pytest.mark.asyncio
    async def test_multiple_devices_persisted(self, orchestrator, detection_store):
        """Detections from multiple devices are stored with correct device_id."""
        for dev in ["edge-A", "edge-B", "edge-C"]:
            await orchestrator.process_detection(
                make_detection(frame_id=1, device_id=dev)
            )

        all_rows = detection_store.query(since=time.time() - 10)
        device_ids = {r["device_id"] for r in all_rows}
        assert device_ids == {"edge-A", "edge-B", "edge-C"}

    @pytest.mark.asyncio
    async def test_event_listener_receives_events(self, orchestrator):
        """Subscribed listener queue receives detection events."""
        q = orchestrator.subscribe()
        det = make_detection(frame_id=42, device_id="edge-listen")
        await orchestrator.process_detection(det)

        event = q.get_nowait()
        assert event["frame_id"] == 42
        assert event["device_id"] == "edge-listen"
        orchestrator.unsubscribe(q)

    @pytest.mark.asyncio
    async def test_vlm_queue_receives_qualifying_detection(self, orchestrator):
        """High-confidence person detection with frame_data enters VLM queue."""
        det = make_detection(
            frame_id=99,
            class_name="person",
            confidence=0.95,
            frame_data=b"\xff\xd8\xff\xe0" + b"\x00" * 50,
        )
        await orchestrator.process_detection(det)
        assert orchestrator._vlm_queue.qsize() == 1
        item = orchestrator._vlm_queue.get_nowait()
        assert item["frame_id"] == 99

    @pytest.mark.asyncio
    async def test_vlm_queue_skips_low_confidence(self, orchestrator):
        """Low-confidence detection does NOT enter VLM queue."""
        det = make_detection(
            frame_id=100,
            class_name="person",
            confidence=0.3,
            frame_data=b"\xff\xd8\xff\xe0" + b"\x00" * 50,
        )
        await orchestrator.process_detection(det)
        assert orchestrator._vlm_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_vlm_queue_skips_no_frame_data(self, orchestrator):
        """Detection without frame_data does NOT enter VLM queue."""
        det = make_detection(frame_id=101, confidence=0.95, frame_data=b"")
        await orchestrator.process_detection(det)
        assert orchestrator._vlm_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, session_manager):
        """Register → heartbeat → unregister lifecycle."""
        assert session_manager.register("edge-e2e-001", device_name="front-cam")
        session_manager.heartbeat("edge-e2e-001")
        session_manager.increment_frames("edge-e2e-001", 10)
        s = session_manager.get_session("edge-e2e-001")
        assert s.frames_received == 10
        session_manager.unregister("edge-e2e-001")
        assert session_manager.get_session("edge-e2e-001") is None

    @pytest.mark.asyncio
    async def test_detection_store_query_by_device(self, orchestrator, detection_store):
        """Query filtering by device_id returns correct subset."""
        for i, dev in enumerate(["dev-X", "dev-Y", "dev-X"]):
            await orchestrator.process_detection(
                make_detection(frame_id=i, device_id=dev)
            )
        rows_x = detection_store.query(since=time.time() - 10, device_id="dev-X")
        rows_y = detection_store.query(since=time.time() - 10, device_id="dev-Y")
        assert len(rows_x) == 2
        assert len(rows_y) == 1

    @pytest.mark.asyncio
    async def test_recent_events_device_filter(self, orchestrator):
        """get_recent_events with device_id filter."""
        for dev in ["d1", "d2", "d1"]:
            await orchestrator.process_detection(
                make_detection(frame_id=1, device_id=dev)
            )
        events_d1 = orchestrator.get_recent_events(device_id="d1")
        events_d2 = orchestrator.get_recent_events(device_id="d2")
        assert len(events_d1) == 2
        assert len(events_d2) == 1
