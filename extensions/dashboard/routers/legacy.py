"""Legacy v1 API routes for backward compatibility."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from ..middleware import verify_credentials
from ..services import events, session_manager, start_time

router = APIRouter(prefix="/api", tags=["legacy"])


def _demo_status() -> dict:
    """Generate demo status when running standalone."""
    uptime = time.time() - start_time
    return {
        "edge": {
            "status": "connected",
            "fps": 28.5,
            "npu_usage": 72.0,
            "temperature": 55.0,
            "model": "yolov5s-640-640.rknn",
        },
        "central": {
            "status": "running",
            "model": "Llama-3.2-3B-Instruct-4bit-mlx",
            "uptime_s": round(uptime),
            "events_processed": len(events),
        },
    }


@router.get("/status")
async def api_status(_=Depends(verify_credentials)):
    """Get demo status."""
    return _demo_status()


@router.get("/events")
async def api_events(
    limit: int = 50,
    device_id: str = "",
    _=Depends(verify_credentials),
):
    """Get recent events."""
    if device_id:
        filtered = [e for e in events if e.get("device_id") == device_id]
        return filtered[-limit:]
    return events[-limit:]


@router.get("/events/history")
async def api_events_history(
    hours: float = Query(24, ge=0.1, le=720),
    limit: int = Query(100, ge=1, le=1000),
    device_id: str = "",
    _=Depends(verify_credentials),
):
    """Query historical events from SQLite store."""
    from ..services import detection_store

    if detection_store is None:
        return {"error": "No persistent store configured", "events": []}

    since = time.time() - hours * 3600
    stored_events = detection_store.query(since=since, limit=limit, device_id=device_id)
    return {"count": len(stored_events), "hours": hours, "events": stored_events}


@router.get("/devices")
async def api_devices(_=Depends(verify_credentials)):
    """List all connected edge devices."""
    if session_manager is None:
        return []

    sessions = session_manager.list_sessions()
    return [
        {
            "device_id": s.device_id,
            "device_name": s.device_name,
            "status": s.status,
            "connected_at": s.connected_at,
            "last_heartbeat": s.last_heartbeat,
            "frames_received": s.frames_received,
        }
        for s in sessions
    ]


@router.get("/devices/{device_id}/events")
async def api_device_events(
    device_id: str,
    limit: int = 50,
    _=Depends(verify_credentials),
):
    """Get events for a specific device."""
    filtered = [e for e in events if e.get("device_id") == device_id]
    return filtered[-limit:]


# Template rendering for HTMX frontend
def get_templates():
    """Lazy load templates to avoid path issues."""
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    return Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, _=Depends(verify_credentials)):
    """Render main dashboard page."""
    templates = get_templates()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": _demo_status(),
        "events": events[-20:],
    })
