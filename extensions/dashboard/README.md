# Neuro-Pipeline Dashboard

FastAPI-based monitoring and management API for the Neuro-Pipeline system. Provides both a lightweight HTMX frontend and a comprehensive REST API for the neuro-dashboard React application.

## Features

- **System Monitoring**: Real-time status of Edge devices and Central server
- **Event Streaming**: WebSocket-based live event updates
- **Model Management**: Deploy, switch, and rollback models on edge devices
- **A/B Testing**: Traffic split management and variant metrics
- **Configuration Management**: YAML config editor with validation
- **Behavior Analysis**: Real-time behavior event monitoring
- **Anomaly Detection**: Baseline statistics and Z-score anomaly detection
- **VLM Guidance**: AI-powered configuration suggestions
- **Cross-Camera Tracking**: ReID-based trajectory visualization
- **Auto-Annotation**: Sample collection and COCO/YOLO export

## Quick Start

### Standalone Mode (Demo Data)

```bash
cd extensions/dashboard
pip install -r requirements.txt

# Set auth credentials (optional)
export DASHBOARD_USER=admin
export DASHBOARD_PASS=your_password

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000 in your browser.

### Integrated Mode (from Central Server)

```python
from extensions.dashboard import app, inject_from_central

# Inject services from central server
inject_from_central(
    detection_store=store,
    session_manager=sessions,
    orchestrator=orch,
    health_checker=checker,
    ab_test_manager=ab_test,
    model_registry=registry,
    config_path="config.yaml",
)

# Mount in FastAPI app or run with uvicorn
```

## Package Structure

```
extensions/dashboard/
├── __init__.py              # Package exports
├── app.py                   # Main FastAPI application
├── README.md
├── requirements.txt
│
├── routers/
│   ├── legacy.py            # v1 API (backward compatibility)
│   └── v2/
│       ├── status.py        # System status, devices, events
│       ├── models.py        # Model management, A/B testing
│       ├── config.py        # Configuration management
│       ├── intelligence.py  # Behavior, anomaly, VLM guidance
│       └── tracking.py      # ReID, reports, annotator, users
│
├── services/
│   ├── state.py             # Global state & dependency injection
│   ├── demo_data.py         # Demo data generators
│   └── validators.py        # Configuration validation
│
├── middleware/
│   └── auth.py              # HTTP Basic Auth
│
└── templates/               # Jinja2 templates for HTMX frontend
```

## API Reference

### Health & Metrics

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/healthz` | GET | No | Liveness probe |
| `/readyz` | GET | No | Readiness probe |
| `/metrics` | GET | No | Prometheus metrics |

### Legacy v1 API

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | Yes | HTMX dashboard page |
| `/api/status` | GET | Yes | System status JSON |
| `/api/devices` | GET | Yes | Registered devices list |
| `/api/events` | GET/POST | Yes | Recent events / Push event |
| `/api/events/history` | GET | Yes | SQLite history |
| `/ws` | WS | Yes | Real-time event stream |

### v2 API

#### System Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/status` | GET | Aggregated system status |
| `/api/v2/devices` | GET | Device list with metrics |
| `/api/v2/events` | GET | Events with filters |
| `/api/v2/events/history` | GET | Historical events |
| `/api/v2/command` | POST | Send control command |

#### Model Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/models` | GET | List all models |
| `/api/v2/models/{id}/switch` | POST | Switch active model |
| `/api/v2/models/reload` | POST | Reload all models |
| `/api/v2/models/{id}/rollback` | POST | Rollback model version |

#### A/B Testing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/ab-test` | GET | Get A/B test results |
| `/api/v2/ab-test/split` | POST | Adjust traffic split |
| `/api/v2/ab-test/reset` | POST | Reset test metrics |

#### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/config` | GET | Get current config |
| `/api/v2/config` | PUT | Update config |
| `/api/v2/config/dry-run` | POST | Validate without applying |

#### Intelligence (v2)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/behavior/events` | GET | Behavior analysis events |
| `/api/v2/anomaly/baselines` | GET | Baseline statistics |
| `/api/v2/anomaly/scores` | GET | Anomaly scores |
| `/api/v2/vlm/guidance` | GET | VLM config suggestions |
| `/api/v2/vlm/guidance/{id}/apply` | POST | Apply suggestion |

#### Tracking & Reports

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/reports/generate` | POST | Generate report |
| `/api/v2/reports/{id}` | GET | Get report |
| `/api/v2/reid/tracks` | GET | ReID cross-camera tracks |
| `/api/v2/reid/tracks/{id}` | GET | Track details |

#### Auto-Annotator

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/annotator/samples` | GET | Annotated samples |
| `/api/v2/annotator/export` | GET | Export (COCO/YOLO) |

#### User Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/users` | GET | List users |
| `/api/v2/users` | POST | Create user |
| `/api/v2/users/{id}` | PUT | Update user |
| `/api/v2/users/{id}` | DELETE | Delete user |

## Authentication

HTTP Basic Auth is supported via environment variables:

| Variable | Description |
|----------|-------------|
| `DASHBOARD_USER` | Username |
| `DASHBOARD_PASS` | Password |

If not set, authentication is disabled (all requests allowed).

## Integration Examples

### Push Events from Orchestrator

```python
import httpx

async with httpx.AsyncClient() as client:
    await client.post(
        "http://localhost:8000/api/v2/events",
        json={
            "device_id": "edge-001",
            "type": "DETECTION_ALERT",
            "severity": "warning",
            "description": "Person detected",
            "boxes": [{"class_name": "person", "confidence": 0.95}],
        },
        auth=("admin", "password"),
    )
```

### Send Control Command

```python
import httpx

async with httpx.AsyncClient() as client:
    await client.post(
        "http://localhost:8000/api/v2/command",
        json={
            "type": "SWITCH_MODEL_VARIANT",
            "parameters": {"model_id": "yolov8s-rk3588"},
            "commandId": 12345,
        },
        auth=("admin", "password"),
    )
```

### WebSocket Real-time Events

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Event:", data);
};
```

## Testing

```bash
# Run dashboard tests
pytest extensions/dashboard/tests/ -v

# Run with coverage
pytest extensions/dashboard/tests/ --cov=extensions/dashboard --cov-report=html
```

## Dependencies

- FastAPI
- uvicorn
- PyYAML
- prometheus-client
- Jinja2
