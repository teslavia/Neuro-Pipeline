"""Demo data generators for standalone dashboard mode.

These functions generate realistic demo data when the dashboard is run
without injected services from the central server.
"""

import random
import time
from datetime import datetime, timezone

from ..services import state


# ── Demo Models ──────────────────────────────────────

def get_demo_models() -> list[dict]:
    """Generate demo model records."""
    return [
        {
            "modelId": "yolov5s-rk3588",
            "modelPath": "/opt/neuro-pipeline/models/yolov5s-640-640.rknn",
            "modelType": "detection",
            "version": "v1.0.0",
            "status": "deployed",
            "npuCore": 0,
            "deployedAt": time.time() - 3600,
            "targetDeviceId": "edge-001",
            "metadata": {"size_mb": 8, "avg_confidence": 0.55},
        },
        {
            "modelId": "yolov5m-rk3588",
            "modelPath": "/opt/neuro-pipeline/models/yolov5m-640-640.rknn",
            "modelType": "detection",
            "version": "v1.0.0",
            "status": "deployed",
            "npuCore": 1,
            "deployedAt": time.time() - 3600,
            "targetDeviceId": "edge-001",
            "metadata": {"size_mb": 23, "avg_confidence": 0.62},
        },
        {
            "modelId": "yolov8s-rk3588",
            "modelPath": "/opt/neuro-pipeline/models/yolov8s-640-640.rknn",
            "modelType": "detection",
            "version": "v1.0.0",
            "status": "deployed",
            "npuCore": 2,
            "deployedAt": time.time() - 3600,
            "targetDeviceId": "edge-001",
            "metadata": {"size_mb": 12, "avg_confidence": 0.78},
        },
    ]


# ── Demo Behavior Events ──────────────────────────────────────

BEHAVIOR_TYPES = ["LOITERING", "RUNNING", "CROWD", "FALL", "INTRUSION", "ABANDONED_OBJECT"]
DEMO_DEVICES = ["device-1", "device-2", "device-3"]


def get_demo_behavior_events(
    device_id: str = "",
    behavior_type: str = "",
    limit: int = 50,
) -> list[dict]:
    """Generate demo behavior analysis events."""
    devices = DEMO_DEVICES if not device_id else [device_id]

    events = []
    for i in range(min(limit, 20)):
        btype = behavior_type if behavior_type else random.choice(BEHAVIOR_TYPES)
        dev = random.choice(devices)
        events.append({
            "id": f"behavior-{i+1}",
            "deviceId": dev,
            "behaviorType": btype,
            "confidence": round(random.uniform(0.7, 0.99), 2),
            "timestamp": datetime.fromtimestamp(
                time.time() - i * 300, tz=timezone.utc
            ).isoformat(),
            "trackId": f"track-{random.randint(100, 999)}",
            "boundingBox": _random_bbox(),
            "metadata": {"duration_seconds": random.randint(5, 60)},
        })
    return events


# ── Demo Anomaly Data ──────────────────────────────────────

def get_demo_baselines() -> list[dict]:
    """Generate demo baseline statistics."""
    return [
        {
            "metricName": "detections_per_hour",
            "mean": 45.2,
            "stdDev": 12.3,
            "sampleCount": 168,
            "lastUpdated": datetime.now(tz=timezone.utc).isoformat(),
        },
        {
            "metricName": "avg_confidence",
            "mean": 0.72,
            "stdDev": 0.08,
            "sampleCount": 168,
            "lastUpdated": datetime.now(tz=timezone.utc).isoformat(),
        },
        {
            "metricName": "latency_ms",
            "mean": 22.5,
            "stdDev": 5.1,
            "sampleCount": 168,
            "lastUpdated": datetime.now(tz=timezone.utc).isoformat(),
        },
    ]


def get_demo_anomaly_scores(
    device_id: str = "",
    hours: int = 24,
) -> list[dict]:
    """Generate demo anomaly scores."""
    devices = DEMO_DEVICES if not device_id else [device_id]
    metrics = ["detections_per_hour", "avg_confidence", "latency_ms"]

    scores = []
    for i in range(min(hours * 2, 48)):
        metric = random.choice(metrics)
        z = random.gauss(0, 1)
        is_anomaly = abs(z) > 3
        if is_anomaly:
            z = random.choice([-1, 1]) * random.uniform(3.1, 5.0)

        scores.append({
            "id": f"anomaly-{i+1}",
            "deviceId": random.choice(devices),
            "metricName": metric,
            "zScore": round(z, 2),
            "isAnomaly": is_anomaly,
            "timestamp": datetime.fromtimestamp(
                time.time() - i * 1800, tz=timezone.utc
            ).isoformat(),
            "value": round(random.uniform(10, 100), 1),
        })
    return scores


# ── Demo VLM Guidance ──────────────────────────────────────

def get_demo_vlm_guidance(device_id: str = "") -> list[dict]:
    """Generate demo VLM configuration guidance."""
    return [
        {
            "id": "guidance-1",
            "deviceId": device_id or "device-1",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "analysis": "检测到夜间场景中置信度较低，建议降低阈值以提高召回率",
            "adjustments": [
                {
                    "parameter": "confidence_threshold",
                    "currentValue": 0.5,
                    "suggestedValue": 0.35,
                    "reason": "夜间低光环境下建议降低阈值",
                    "impact": "medium",
                },
                {
                    "parameter": "fps",
                    "currentValue": 30,
                    "suggestedValue": 15,
                    "reason": "夜间低活动期可降低帧率以节省资源",
                    "impact": "low",
                },
            ],
            "applied": False,
        },
        {
            "id": "guidance-2",
            "deviceId": device_id or "device-2",
            "timestamp": datetime.fromtimestamp(
                time.time() - 3600, tz=timezone.utc
            ).isoformat(),
            "analysis": "高峰期检测延迟较高，建议启用自适应帧率",
            "adjustments": [
                {
                    "parameter": "adaptive_fps.enabled",
                    "currentValue": False,
                    "suggestedValue": True,
                    "reason": "启用自适应帧率可动态调整负载",
                    "impact": "high",
                },
            ],
            "applied": False,
        },
    ]


# ── Demo ReID Tracks ──────────────────────────────────────

def get_demo_reid_tracks(device_id: str = "", limit: int = 50) -> list[dict]:
    """Generate demo ReID cross-camera tracks."""
    tracks = []
    for i in range(min(limit, 10)):
        appearances = []
        for _ in range(random.randint(2, 4)):
            appearances.append({
                "deviceId": random.choice(DEMO_DEVICES),
                "timestamp": datetime.fromtimestamp(
                    time.time() - random.randint(0, 3600), tz=timezone.utc
                ).isoformat(),
                "boundingBox": _random_bbox(),
                "confidence": round(random.uniform(0.75, 0.95), 2),
            })

        first_ts = min(a["timestamp"] for a in appearances)
        last_ts = max(a["timestamp"] for a in appearances)

        tracks.append({
            "trackId": f"reid-{i+1:04d}",
            "globalId": f"global-{1000+i}",
            "appearances": appearances,
            "firstSeen": first_ts,
            "lastSeen": last_ts,
            "totalDuration": random.randint(60, 600),
        })
    return tracks


def get_demo_reid_track(track_id: str) -> dict:
    """Generate a single demo ReID track."""
    appearances = []
    for _ in range(random.randint(3, 5)):
        appearances.append({
            "deviceId": random.choice(DEMO_DEVICES),
            "timestamp": datetime.fromtimestamp(
                time.time() - random.randint(0, 3600), tz=timezone.utc
            ).isoformat(),
            "boundingBox": _random_bbox(),
            "confidence": round(random.uniform(0.75, 0.95), 2),
        })

    return {
        "trackId": track_id,
        "globalId": "global-1001",
        "appearances": appearances,
        "firstSeen": appearances[0]["timestamp"],
        "lastSeen": appearances[-1]["timestamp"],
        "totalDuration": random.randint(120, 900),
    }


# ── Demo Annotated Samples ──────────────────────────────────────

def get_demo_annotated_samples(
    verified: Optional[bool] = None,
    limit: int = 50,
) -> list[dict]:
    """Generate demo annotated samples."""
    samples = []
    for i in range(min(limit, 20)):
        samples.append({
            "id": f"sample-{i+1}",
            "imageUrl": f"/api/v2/annotator/samples/{i+1}/image",
            "annotations": [_random_bbox()["boundingBox"] for _ in range(1)],
            "sourceDevice": random.choice(DEMO_DEVICES),
            "capturedAt": datetime.fromtimestamp(
                time.time() - random.randint(0, 86400), tz=timezone.utc
            ).isoformat(),
            "verified": random.choice([True, False]) if verified is None else verified,
        })
    return samples


# ── Demo Users ──────────────────────────────────────

DEMO_USERS = [
    {"id": "user-1", "username": "admin", "role": "admin", "email": "admin@example.com", "createdAt": "2026-01-01T00:00:00Z"},
    {"id": "user-2", "username": "operator", "role": "operator", "email": "operator@example.com", "createdAt": "2026-01-15T00:00:00Z"},
]


def get_demo_users() -> list[dict]:
    """Get demo user list."""
    return DEMO_USERS.copy()


def add_demo_user(username: str, role: str, email: str) -> dict:
    """Add a demo user."""
    new_user = {
        "id": f"user-{len(DEMO_USERS)+1}",
        "username": username,
        "role": role,
        "email": email,
        "createdAt": datetime.now(tz=timezone.utc).isoformat(),
    }
    DEMO_USERS.append(new_user)
    return new_user


def update_demo_user(user_id: str, updates: dict) -> Optional[dict]:
    """Update a demo user."""
    for user in DEMO_USERS:
        if user["id"] == user_id:
            user.update(updates)
            return user
    return None


def delete_demo_user(user_id: str) -> bool:
    """Delete a demo user."""
    global DEMO_USERS
    original_len = len(DEMO_USERS)
    DEMO_USERS = [u for u in DEMO_USERS if u["id"] != user_id]
    return len(DEMO_USERS) < original_len


# ── Helper Functions ──────────────────────────────────────

def _random_bbox() -> dict:
    """Generate a random bounding box."""
    return {
        "boundingBox": {
            "classId": 0,
            "className": "person",
            "confidence": round(random.uniform(0.8, 0.95), 2),
            "xMin": round(random.uniform(0.1, 0.4), 2),
            "yMin": round(random.uniform(0.1, 0.4), 2),
            "xMax": round(random.uniform(0.5, 0.9), 2),
            "yMax": round(random.uniform(0.5, 0.9), 2),
        }
    }


# Import Optional for type hint
from typing import Optional
