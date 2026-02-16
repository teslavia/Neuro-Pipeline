"""Neuro-Pipeline Dashboard — FastAPI + htmx real-time monitoring."""

import asyncio
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED

app = FastAPI(title="Neuro-Pipeline Dashboard")

# CORS — allow neuro-dashboard frontend (Next.js dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
security = HTTPBasic(auto_error=False)

# In-memory event store (standalone mode without orchestrator)
_events: list[dict] = []
_ws_clients: list[WebSocket] = []
_start_time = time.time()

# Optional: injected DetectionStore for persistent history
_detection_store = None

# Optional: injected HealthChecker
_health_checker = None

# Optional: injected DeviceSessionManager
_session_manager = None

# Optional: injected CentralOrchestrator (for command dispatch)
_orchestrator = None


def set_detection_store(store) -> None:
    """Inject a DetectionStore instance for history queries."""
    global _detection_store
    _detection_store = store


def set_health_checker(checker) -> None:
    """Inject a HealthChecker instance for probes."""
    global _health_checker
    _health_checker = checker


def set_session_manager(manager) -> None:
    """Inject a DeviceSessionManager for multi-device queries."""
    global _session_manager
    _session_manager = manager


def set_orchestrator(orchestrator) -> None:
    """Inject a CentralOrchestrator for command dispatch."""
    global _orchestrator
    _orchestrator = orchestrator


def inject_from_central(*, detection_store=None, session_manager=None,
                        orchestrator=None, health_checker=None):
    """One-call injection from central server process."""
    if detection_store is not None:
        set_detection_store(detection_store)
    if session_manager is not None:
        set_session_manager(session_manager)
    if orchestrator is not None:
        set_orchestrator(orchestrator)
    if health_checker is not None:
        set_health_checker(health_checker)


def _get_auth_credentials():
    """Get dashboard credentials from environment variables."""
    username = os.environ.get("DASHBOARD_USER", "")
    password = os.environ.get("DASHBOARD_PASS", "")
    return username, password


def verify_credentials(
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    """Verify HTTP Basic Auth credentials. No-op if env vars not set."""
    expected_user, expected_pass = _get_auth_credentials()
    if not expected_user and not expected_pass:
        return  # Auth not configured, allow all
    if credentials is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    correct_user = secrets.compare_digest(credentials.username, expected_user)
    correct_pass = secrets.compare_digest(credentials.password, expected_pass)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


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
async def index(request: Request, _=Depends(verify_credentials)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": _demo_status(),
        "events": _events[-20:],
    })


@app.get("/api/status")
async def api_status(_=Depends(verify_credentials)):
    return _demo_status()


@app.get("/api/events")
async def api_events(limit: int = 50, device_id: str = "", _=Depends(verify_credentials)):
    if device_id:
        filtered = [e for e in _events if e.get("device_id") == device_id]
        return filtered[-limit:]
    return _events[-limit:]


@app.post("/api/events")
async def post_event(event: dict, _=Depends(verify_credentials)):
    """Receive event from orchestrator or external source."""
    event.setdefault("timestamp", time.time())
    _events.append(event)
    if len(_events) > 500:
        _events.pop(0)
    # Broadcast normalized v2 format to WebSocket clients
    normalized = _normalize_event(event)
    msg = json.dumps(normalized)
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
    device_id: str = "",
    _=Depends(verify_credentials),
):
    """Query historical events from SQLite store."""
    if _detection_store is None:
        return {"error": "No persistent store configured", "events": []}
    since = time.time() - hours * 3600
    events = _detection_store.query(since=since, limit=limit, device_id=device_id)
    return {"count": len(events), "hours": hours, "events": events}


@app.get("/api/devices")
async def api_devices(_=Depends(verify_credentials)):
    """List all connected edge devices."""
    if _session_manager is None:
        return []
    sessions = _session_manager.list_sessions()
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


@app.get("/api/devices/{device_id}/events")
async def api_device_events(device_id: str, limit: int = 50, _=Depends(verify_credentials)):
    """Get events for a specific device."""
    filtered = [e for e in _events if e.get("device_id") == device_id]
    return filtered[-limit:]


@app.get("/metrics")
async def metrics_endpoint(_=Depends(verify_credentials)):
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
async def readyz(_=Depends(verify_credentials)):
    """Readiness probe — 200 if all subsystems ready, 503 otherwise."""
    if _health_checker:
        status = _health_checker.readiness()
        code = 200 if status.ready else 503
        return JSONResponse(
            {"ready": status.ready, "checks": status.checks},
            status_code=code,
        )
    return JSONResponse({"ready": True})


# ── Event normalization (v1 dict → v2 DetectionEvent format) ─────

def _normalize_event(raw: dict) -> dict:
    """Convert internal event dict to frontend DetectionEvent format."""
    ts = raw.get("timestamp", time.time())
    if isinstance(ts, (int, float)):
        ts_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    else:
        ts_iso = str(ts)

    device_id = raw.get("device_id", "unknown")
    event_type = raw.get("type", "DETECTION_ALERT").upper()
    if event_type not in ("DETECTION_ALERT", "SYSTEM_ERROR", "MODEL_LOADED", "HEALTH_UPDATE"):
        event_type = "DETECTION_ALERT"

    severity = raw.get("severity", "info")
    if severity not in ("critical", "warning", "info"):
        conf = raw.get("confidence", 0)
        if event_type == "SYSTEM_ERROR":
            severity = "critical"
        elif isinstance(conf, (int, float)) and conf >= 0.9:
            severity = "warning"
        else:
            severity = "info"

    raw_id = f"{device_id}:{ts}:{event_type}"
    event_id = raw.get("id", hashlib.md5(raw_id.encode()).hexdigest()[:12])

    boxes = []
    for b in raw.get("boxes") or raw.get("detections") or []:
        boxes.append({
            "classId": b.get("class_id", 0),
            "className": b.get("class_name", ""),
            "confidence": b.get("confidence", 0),
            "xMin": b.get("x_min", 0),
            "yMin": b.get("y_min", 0),
            "xMax": b.get("x_max", 0),
            "yMax": b.get("y_max", 0),
        })

    return {
        "id": event_id,
        "deviceId": device_id,
        "deviceName": raw.get("device_name", device_id),
        "type": event_type,
        "severity": severity,
        "description": raw.get("description", raw.get("message", raw.get("class", ""))),
        "timestamp": ts_iso,
        "metadata": {k: str(v) for k, v in raw.get("metadata", {}).items()},
        "boxes": boxes,
        "frameData": raw.get("frame_data"),
    }


def _status_to_connection(status: str) -> str:
    """Map DeviceSession.status to frontend ConnectionStatus."""
    return {"connected": "online", "stale": "degraded"}.get(status, "offline")


# ── v2 API — format matching neuro-dashboard frontend types ──────

@app.get("/api/v2/status")
async def api_v2_status(_=Depends(verify_credentials)):
    """Aggregated system status matching frontend SystemStatus type."""
    devices = []
    if _session_manager:
        devices = _session_manager.list_sessions()

    connected = [d for d in devices if d.status == "connected"]
    total_fps = 0.0
    total_npu = 0.0
    total_temp = 0.0

    # Pull per-device metrics from Prometheus gauges if available
    try:
        from src.observability.metrics import edge_fps, edge_device_status
        for d in connected:
            try:
                fps_val = edge_fps.labels(device_id=d.device_id)._value.get()
                total_fps += fps_val
            except Exception:
                total_fps += 0
    except ImportError:
        total_fps = len(connected) * 28.5  # fallback estimate

    avg_npu = 72.0 if connected else 0.0  # placeholder until per-device NPU gauge
    avg_temp = 55.0 if connected else 0.0

    # Alert counts from in-memory events
    critical = sum(1 for e in _events[-200:] if e.get("severity") == "critical"
                   or e.get("type", "").upper() == "SYSTEM_ERROR")
    warning = sum(1 for e in _events[-200:] if e.get("severity") == "warning")
    info_count = sum(1 for e in _events[-200:] if e.get("severity", "info") == "info"
                     and e.get("type", "").upper() not in ("SYSTEM_ERROR",))

    uptime = time.time() - _start_time
    model_name = "Llama-3.2-3B-Instruct-4bit-mlx"
    inference_mode = "llm"
    vlm_queue = 0

    try:
        from src.observability.metrics import vlm_queue_depth
        vlm_queue = int(vlm_queue_depth._value.get())
    except Exception:
        pass

    return {
        "edge": {
            "connectedDevices": len(connected),
            "totalFps": round(total_fps, 1),
            "avgNpuUsage": round(avg_npu, 1),
            "avgTemperature": round(avg_temp, 1),
        },
        "central": {
            "modelLoaded": model_name,
            "inferenceMode": inference_mode,
            "uptime": round(uptime),
            "vlmQueueDepth": vlm_queue,
        },
        "alerts": {
            "critical": critical,
            "warning": warning,
            "info": info_count,
        },
    }


@app.get("/api/v2/devices")
async def api_v2_devices(_=Depends(verify_credentials)):
    """Device list matching frontend Device type."""
    if _session_manager is None:
        return []
    sessions = _session_manager.list_sessions()
    result = []
    for s in sessions:
        fps = 0.0
        try:
            from src.observability.metrics import edge_fps
            fps = edge_fps.labels(device_id=s.device_id)._value.get()
        except Exception:
            pass

        result.append({
            "id": s.device_id,
            "name": s.device_name or s.device_id,
            "status": _status_to_connection(s.status),
            "firmwareVersion": s.firmware_version,
            "capabilities": s.capabilities,
            "metrics": {
                "cpuUsage": 0,
                "npuUsage": 72.0 if s.status == "connected" else 0,
                "memoryUsedMb": 0,
                "temperatureC": 55.0 if s.status == "connected" else 0,
                "fps": round(fps, 1),
            },
            "lastSeen": datetime.fromtimestamp(
                s.last_heartbeat, tz=timezone.utc
            ).isoformat(),
        })
    return result


@app.get("/api/v2/events")
async def api_v2_events(
    limit: int = Query(50, ge=1, le=200),
    device_id: str = "",
    severity: str = "",
    event_type: str = "",
    _=Depends(verify_credentials),
):
    """Events matching frontend DetectionEvent type."""
    filtered = _events
    if device_id:
        filtered = [e for e in filtered if e.get("device_id") == device_id]
    if severity:
        filtered = [e for e in filtered if e.get("severity") == severity]
    if event_type:
        filtered = [e for e in filtered
                    if e.get("type", "").upper() == event_type.upper()]
    return [_normalize_event(e) for e in filtered[-limit:]]


@app.get("/api/v2/events/history")
async def api_v2_events_history(
    hours: float = Query(24, ge=0.1, le=720),
    limit: int = Query(100, ge=1, le=1000),
    device_id: str = "",
    _=Depends(verify_credentials),
):
    """Historical events from SQLite, normalized to v2 format."""
    if _detection_store is None:
        return {"count": 0, "hours": hours, "events": []}
    since = time.time() - hours * 3600
    raw_events = _detection_store.query(since=since, limit=limit, device_id=device_id)
    events = [_normalize_event(e) for e in raw_events]
    return {"count": len(events), "hours": hours, "events": events}


@app.post("/api/v2/command")
async def api_v2_command(body: dict, _=Depends(verify_credentials)):
    """Send control command to edge device via orchestrator."""
    cmd_type = body.get("type", "")
    parameters = body.get("parameters", {})
    command_id = body.get("commandId", 0)

    if not cmd_type:
        raise HTTPException(status_code=400, detail="Missing command type")

    if _orchestrator is None:
        return {"success": False, "message": "Orchestrator not available"}

    try:
        from src.generated import neuro_pipeline_pb2
        cmd = neuro_pipeline_pb2.ControlCommand()
        type_map = {
            "SET_FPS": neuro_pipeline_pb2.ControlCommand.SET_FPS,
            "CHANGE_MODEL": neuro_pipeline_pb2.ControlCommand.CHANGE_MODEL,
            "ENABLE_DEBUG": neuro_pipeline_pb2.ControlCommand.ENABLE_DEBUG,
            "SET_DETECTION_THRESHOLD": neuro_pipeline_pb2.ControlCommand.SET_DETECTION_THRESHOLD,
            "SHUTDOWN": neuro_pipeline_pb2.ControlCommand.SHUTDOWN,
            "RELOAD_MODEL": neuro_pipeline_pb2.ControlCommand.RELOAD_MODEL,
        }
        cmd.type = type_map.get(cmd_type, 0)
        cmd.command_id = command_id
        for k, v in parameters.items():
            cmd.parameters[k] = str(v)
        await _orchestrator.send_command(cmd)
        return {"success": True, "message": f"Command {cmd_type} queued"}
    except ImportError:
        return {"success": False, "message": "Protobuf not available"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


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
