# Neuro-Pipeline Dashboard

Real-time monitoring dashboard for the Neuro-Pipeline system.

## Quick Start

```bash
cd extensions/dashboard
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080 in your browser.

## Features

- Device status cards (Edge RK3588 + Central Mac Mini)
- Live event stream via WebSocket
- REST API for integration

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard page |
| `/api/status` | GET | System status JSON |
| `/api/events` | GET | Recent events (query: `?limit=50`) |
| `/api/events` | POST | Push event from orchestrator |
| `/ws` | WS | Real-time event stream |

## Integration

The orchestrator pushes events via POST:

```python
import httpx
async with httpx.AsyncClient() as client:
    await client.post("http://localhost:8080/api/events", json={
        "type": "detection",
        "detections": [{"class_name": "person", "confidence": 0.95}],
    })
```
