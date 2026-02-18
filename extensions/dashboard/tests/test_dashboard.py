"""Dashboard endpoint tests."""
import pytest
from httpx import AsyncClient, ASGITransport

from extensions.dashboard.app import app
from extensions.dashboard.services import (
    events, ws_clients, set_session_manager, set_detection_store,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Clear global state between tests."""
    events.clear()
    ws_clients.clear()
    set_session_manager(None)
    set_detection_store(None)
    yield
    events.clear()


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_status_endpoint(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "edge" in data
    assert "central" in data


@pytest.mark.asyncio
async def test_events_empty(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/events")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_post_and_get_events(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/events", json={"type": "detection", "device_id": "e1"})
        await c.post("/api/events", json={"type": "detection", "device_id": "e2"})
        r = await c.get("/api/events")
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_events_device_filter(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/events", json={"type": "det", "device_id": "e1"})
        await c.post("/api/events", json={"type": "det", "device_id": "e2"})
        r = await c.get("/api/events?device_id=e1")
    assert len(r.json()) == 1
    assert r.json()[0]["device_id"] == "e1"


@pytest.mark.asyncio
async def test_device_events_endpoint(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/events", json={"type": "det", "device_id": "e1"})
        await c.post("/api/events", json={"type": "det", "device_id": "e2"})
        r = await c.get("/api/devices/e1/events")
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_devices_no_manager(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/devices")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_devices_with_manager(transport):
    from communication.device_session import DeviceSessionManager
    mgr = DeviceSessionManager(max_devices=4, expiry_timeout=30.0)
    mgr.register("edge-1", "Rock5B", "1.0", ["npu"])
    set_session_manager(mgr)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/devices")
    data = r.json()
    assert len(data) == 1
    assert data[0]["device_id"] == "edge-1"


@pytest.mark.asyncio
async def test_healthz(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["alive"] is True


@pytest.mark.asyncio
async def test_readyz(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/readyz")
    assert r.status_code == 200
    assert r.json()["ready"] is True


@pytest.mark.asyncio
async def test_history_no_store(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/events/history")
    assert r.status_code == 200
    assert "error" in r.json()
