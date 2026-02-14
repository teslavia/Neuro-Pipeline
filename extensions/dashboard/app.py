"""Neuro-Pipeline Dashboard — FastAPI + htmx real-time monitoring."""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI(title="Neuro-Pipeline Dashboard")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# In-memory event store (standalone mode without orchestrator)
_events: list[dict] = []
_ws_clients: list[WebSocket] = []
_start_time = time.time()

# Optional: injected DetectionStore for persistent history
_detection_store = None

# Optional: injected HealthChecker
_health_checker = None


def set_detection_store(store) -> None:
    """Inject a DetectionStore instance for history queries."""
    global _detection_store
    _detection_store = store


def set_health_checker(checker) -> None:
    """Inject a HealthChecker instance for probes."""
    global _health_checker
    _health_checker = checker


def _demo_status() -> dict:
    """Generate demo status when running standalone."""
    uptime = time.time() - _start_time
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
            "events_processed": len(_events),
        },
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": _demo_status(),
        "events": _events[-20:],
    })


@app.get("/api/status")
async def api_status():
    return _demo_status()


@app.get("/api/events")
async def api_events(limit: int = 50):
    return _events[-limit:]


@app.post("/api/events")
async def post_event(event: dict):
    """Receive event from orchestrator or external source."""
    event.setdefault("timestamp", time.time())
    _events.append(event)
    if len(_events) > 500:
        _events.pop(0)
    msg = json.dumps(event)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            _ws_clients.remove(ws)
    return {"ok": True}


@app.get("/api/events/history")
async def api_events_history(
    hours: float = Query(24, ge=0.1, le=720),
    limit: int = Query(100, ge=1, le=1000),
):
    """Query historical events from SQLite store."""
    if _detection_store is None:
        return {"error": "No persistent store configured", "events": []}
    since = time.time() - hours * 3600
    events = _detection_store.query(since=since, limit=limit)
    return {"count": len(events), "hours": hours, "events": events}


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics in text exposition format."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz():
    """Liveness probe — always 200 if process is running."""
    if _health_checker:
        status = _health_checker.liveness()
        return JSONResponse({"alive": status.alive, "checks": status.checks})
    return JSONResponse({"alive": True})


@app.get("/readyz")
async def readyz():
    """Readiness probe — 200 if all subsystems ready, 503 otherwise."""
    if _health_checker:
        status = _health_checker.readiness()
        code = 200 if status.ready else 503
        return JSONResponse(
            {"ready": status.ready, "checks": status.checks},
            status_code=code,
        )
    return JSONResponse({"ready": True})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
