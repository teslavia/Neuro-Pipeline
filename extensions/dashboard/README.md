# Neuro-Pipeline Dashboard

Real-time monitoring dashboard for the Neuro-Pipeline system.

## Quick Start

```bash
cd extensions/dashboard
pip install -r requirements.txt

# Set auth credentials
export DASHBOARD_USER=admin
export DASHBOARD_PASS=your_password

uvicorn app:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080 in your browser.

## Authentication (v1.3.0+)

All routes except `/healthz` require HTTP Basic Auth. Credentials are read from environment variables:

| Variable | Description |
|----------|-------------|
| `DASHBOARD_USER` | Username (required) |
| `DASHBOARD_PASS` | Password (required) |

`/healthz` is exempt for health check probes.

## Features

- Device status cards (Edge RK3588 + Central Mac Mini)
- Live event stream via WebSocket
- REST API for integration
- Multi-device view with device_id filtering
- Detection history from SQLite

## API

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | Yes | Dashboard page |
| `/healthz` | GET | No | Health check |
| `/api/status` | GET | Yes | System status JSON |
| `/api/devices` | GET | Yes | Registered devices list |
| `/api/events` | GET | Yes | Recent events (`?limit=50&device_id=xxx`) |
| `/api/events` | POST | Yes | Push event from orchestrator |
| `/api/events/history` | GET | Yes | SQLite history (`?hours=24&limit=100`) |
| `/ws` | WS | Yes | Real-time event stream |

## Integration

The orchestrator pushes events via POST:

```python
import httpx
async with httpx.AsyncClient() as client:
    await client.post("http://localhost:8080/api/events", json={
        "type": "detection",
        "detections": [{"class_name": "person", "confidence": 0.95}],
    }, auth=("admin", "password"))
```
