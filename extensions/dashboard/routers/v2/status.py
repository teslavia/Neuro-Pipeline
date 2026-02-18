"""V2 API routes for system status, devices, and events."""

import hashlib
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ...middleware import verify_credentials
from ...services import (
    events,
    ws_clients,
    session_manager,
    start_time,
)

router = APIRouter(tags=["v2-status"])


# ── Helper Functions ──────────────────────────────────────

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


# ── Status Endpoints ──────────────────────────────────────

@router.get("/api/v2/status")
async def api_v2_status(_=Depends(verify_credentials)):
    """Aggregated system status matching frontend SystemStatus type."""
    devices = []
    if session_manager:
        devices = session_manager.list_sessions()

    connected = [d for d in devices if d.status == "connected"]
    total_fps = 0.0

    # Pull per-device metrics from Prometheus gauges if available
    try:
        from src.observability.metrics import edge_fps
        for d in connected:
            try:
                fps_val = edge_fps.labels(device_id=d.device_id)._value.get()
                total_fps += fps_val
            except Exception:
                pass
    except ImportError:
        total_fps = len(connected) * 28.5  # fallback estimate

    avg_npu = 72.0 if connected else 0.0
    avg_temp = 55.0 if connected else 0.0

    # Alert counts from in-memory events
    critical = sum(
        1 for e in events[-200:]
        if e.get("severity") == "critical" or e.get("type", "").upper() == "SYSTEM_ERROR"
    )
    warning = sum(1 for e in events[-200:] if e.get("severity") == "warning")
    info_count = sum(
        1 for e in events[-200:]
        if e.get("severity", "info") == "info" and e.get("type", "").upper() not in ("SYSTEM_ERROR",)
    )

    uptime = time.time() - start_time
    model_name = "Llama-3.2-3B-Instruct-4bit-mlx"
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
            "inferenceMode": "llm",
            "uptime": round(uptime),
            "vlmQueueDepth": vlm_queue,
        },
        "alerts": {
            "critical": critical,
            "warning": warning,
            "info": info_count,
        },
    }


# ── Device Endpoints ──────────────────────────────────────

@router.get("/api/v2/devices")
async def api_v2_devices(_=Depends(verify_credentials)):
    """Device list matching frontend Device type."""
    if session_manager is None:
        return []

    sessions = session_manager.list_sessions()
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


# ── Event Endpoints ──────────────────────────────────────

@router.get("/api/v2/events")
async def api_v2_events(
    limit: int = Query(50, ge=1, le=200),
    device_id: str = "",
    severity: str = "",
    event_type: str = "",
    _=Depends(verify_credentials),
):
    """Events matching frontend DetectionEvent type."""
    filtered = events
    if device_id:
        filtered = [e for e in filtered if e.get("device_id") == device_id]
    if severity:
        filtered = [e for e in filtered if e.get("severity") == severity]
    if event_type:
        filtered = [e for e in filtered if e.get("type", "").upper() == event_type.upper()]
    return [_normalize_event(e) for e in filtered[-limit:]]


@router.get("/api/v2/events/history")
async def api_v2_events_history(
    hours: float = Query(24, ge=0.1, le=720),
    limit: int = Query(100, ge=1, le=1000),
    device_id: str = "",
    _=Depends(verify_credentials),
):
    """Historical events from SQLite, normalized to v2 format."""
    from ...services import detection_store

    if detection_store is None:
        return {"count": 0, "hours": hours, "events": []}

    since = time.time() - hours * 3600
    raw_events = detection_store.query(since=since, limit=limit, device_id=device_id)
    normalized = [_normalize_event(e) for e in raw_events]
    return {"count": len(normalized), "hours": hours, "events": normalized}


@router.post("/api/v2/events")
async def post_event(event: dict, _=Depends(verify_credentials)):
    """Receive event from orchestrator or external source."""
    event.setdefault("timestamp", time.time())
    events.append(event)
    if len(events) > 500:
        events.pop(0)

    # Broadcast normalized v2 format to WebSocket clients
    normalized = _normalize_event(event)
    msg = json.dumps(normalized)
    for ws in list(ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            ws_clients.remove(ws)

    return {"ok": True}


# ── Command Endpoint ──────────────────────────────────────

@router.post("/api/v2/command")
async def api_v2_command(body: dict, _=Depends(verify_credentials)):
    """Send control command to edge device via orchestrator."""
    from ...services import orchestrator

    cmd_type = body.get("type", "")
    parameters = body.get("parameters", {})
    command_id = body.get("commandId", 0)

    if not cmd_type:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Missing command type")

    if orchestrator is None:
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
        await orchestrator.send_command(cmd)
        return {"success": True, "message": f"Command {cmd_type} queued"}
    except ImportError:
        return {"success": False, "message": "Protobuf not available"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# ── WebSocket ──────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for real-time event streaming."""
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)
