"""Neuro-Pipeline Dashboard — FastAPI + htmx real-time monitoring."""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI(title="Neuro-Pipeline Dashboard")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# In-memory event store (standalone mode without orchestrator)
_events: list[dict] = []
_ws_clients: list[WebSocket] = []
_start_time = time.time()


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
