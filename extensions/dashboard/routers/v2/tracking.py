"""V2 API routes for ReID tracking, reports, auto-annotation, and user management."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...middleware import verify_credentials
from ...services import (
    get_demo_reid_tracks,
    get_demo_reid_track,
    get_demo_annotated_samples,
    get_demo_users,
    add_demo_user,
    update_demo_user,
    delete_demo_user,
    reid_engine,
    auto_annotator,
    report_generator,
)

router = APIRouter(tags=["v2-tracking"])


# ── Report Generation ──────────────────────────────────────

@router.post("/api/v2/reports/generate")
async def api_v2_reports_generate(body: dict, _=Depends(verify_credentials)):
    """Generate a report for the specified time period."""
    import time

    start = body.get("start")
    end = body.get("end")
    title = body.get("title", "Detection Report")
    device_id = body.get("device_id", "")

    if not start or not end:
        raise HTTPException(status_code=400, detail="Missing start or end date")

    # Use real report generator if available
    if report_generator is not None:
        # Parse time range (assume ISO format or hours)
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            hours = (end_dt - start_dt).total_seconds() / 3600
        except Exception:
            hours = 24.0

        report = report_generator.generate(
            device_id=device_id,
            time_range_hours=hours,
            include_vlm=True,
        )
        return {
            "id": report.report_id,
            "title": title,
            "generatedAt": datetime.fromtimestamp(report.generated_at, tz=timezone.utc).isoformat(),
            "period": {"start": start, "end": end},
            "summary": report.summary,
            "totalEvents": report.total_events,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "eventCount": s.event_count,
                    "severity": s.severity,
                }
                for s in report.sections
            ],
        }

    # Fallback to demo data
    report_id = f"report-{int(time.time())}"
    return {
        "id": report_id,
        "title": title,
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "period": {"start": start, "end": end},
        "sections": [
            {
                "title": "执行摘要",
                "content": "报告期间共检测到 1,234 个目标，平均置信度 72.5%。",
            },
            {
                "title": "趋势分析",
                "content": "检测量较上周增长 12%，主要集中在入口区域。",
            },
            {
                "title": "建议",
                "content": "建议在高峰期增加 NPU 核心分配以提高吞吐量。",
            },
        ],
    }


@router.get("/api/v2/reports/{report_id}")
async def api_v2_reports_get(report_id: str, _=Depends(verify_credentials)):
    """Get a generated report by ID."""
    return {
        "id": report_id,
        "title": "Detection Report",
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "period": {"start": "2026-02-01", "end": "2026-02-18"},
        "sections": [
            {"title": "执行摘要", "content": "报告期间共检测到 1,234 个目标，平均置信度 72.5%。"},
            {"title": "趋势分析", "content": "检测量较上周增长 12%，主要集中在入口区域。"},
            {"title": "建议", "content": "建议在高峰期增加 NPU 核心分配以提高吞吐量。"},
        ],
    }


# ── ReID Tracking ──────────────────────────────────────

@router.get("/api/v2/reid/tracks")
async def api_v2_reid_tracks(
    device_id: str = "",
    limit: int = Query(50, ge=1, le=200),
    _=Depends(verify_credentials),
):
    """Query ReID cross-camera tracks."""
    # Use real ReID engine if available
    if reid_engine is not None:
        tracks = reid_engine.list_tracks(min_sightings=2)
        result = []
        for t in tracks[:limit]:
            sightings = [
                {
                    "deviceId": s["device_id"],
                    "timestamp": datetime.fromtimestamp(s["timestamp"], tz=timezone.utc).isoformat(),
                    "similarity": s.get("similarity", 1.0),
                }
                for s in t.sightings
            ]
            result.append({
                "trackId": t.track_id,
                "globalId": t.track_id,
                "className": t.class_name,
                "appearances": sightings,
                "firstSeen": sightings[0]["timestamp"] if sightings else None,
                "lastSeen": sightings[-1]["timestamp"] if sightings else None,
                "totalSightings": len(t.sightings),
            })
        return result

    # Fallback to demo data
    return get_demo_reid_tracks(device_id, limit)


@router.get("/api/v2/reid/tracks/{track_id}")
async def api_v2_reid_track_get(track_id: str, _=Depends(verify_credentials)):
    """Get a specific ReID track by ID."""
    # Use real ReID engine if available
    if reid_engine is not None:
        t = reid_engine.get_track(track_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Track not found")
        sightings = [
            {
                "deviceId": s["device_id"],
                "timestamp": datetime.fromtimestamp(s["timestamp"], tz=timezone.utc).isoformat(),
                "similarity": s.get("similarity", 1.0),
            }
            for s in t.sightings
        ]
        return {
            "trackId": t.track_id,
            "globalId": t.track_id,
            "className": t.class_name,
            "appearances": sightings,
            "firstSeen": sightings[0]["timestamp"] if sightings else None,
            "lastSeen": sightings[-1]["timestamp"] if sightings else None,
            "totalSightings": len(t.sightings),
        }

    # Fallback to demo data
    return get_demo_reid_track(track_id)


# ── Auto-Annotator ──────────────────────────────────────

@router.get("/api/v2/annotator/samples")
async def api_v2_annotator_samples(
    verified: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    _=Depends(verify_credentials),
):
    """Query auto-annotated samples."""
    # Use real auto annotator if available
    if auto_annotator is not None:
        samples = auto_annotator.collect_samples(hours=24.0, limit=limit)
        result = []
        for s in samples:
            annotations = [
                {
                    "className": a["class_name"],
                    "confidence": a["confidence"],
                    "boundingBox": {
                        "xMin": a["x_min"],
                        "yMin": a["y_min"],
                        "xMax": a["x_max"],
                        "yMax": a["y_max"],
                    },
                }
                for a in s.annotations
            ]
            result.append({
                "id": f"sample-{s.image_id}",
                "imageUrl": f"/api/v2/annotator/samples/{s.image_id}/image",
                "annotations": annotations,
                "sourceDevice": s.device_id,
                "capturedAt": datetime.fromtimestamp(s.timestamp, tz=timezone.utc).isoformat(),
                "verified": verified if verified is not None else False,
            })
        return result

    # Fallback to demo data
    return get_demo_annotated_samples(verified, limit)


@router.get("/api/v2/annotator/export")
async def api_v2_annotator_export(format: str = "coco", _=Depends(verify_credentials)):
    """Export annotated samples in COCO or YOLO format."""
    if format not in ("coco", "yolo"):
        raise HTTPException(status_code=400, detail="Format must be 'coco' or 'yolo'")

    # Use real auto annotator if available
    if auto_annotator is not None:
        samples = auto_annotator.collect_samples(hours=24.0, limit=500)
        if format == "coco":
            data = auto_annotator.export_coco(samples)
            return {
                "format": "coco",
                "count": len(samples),
                "data": data,
            }
        else:
            lines = auto_annotator.export_yolo(samples)
            return {
                "format": "yolo",
                "count": len(samples),
                "data": lines,
            }

    # Fallback to demo data
    return {
        "url": f"/exports/annotations.{format}.zip",
        "count": 150,
    }


# ── User Management ──────────────────────────────────────

@router.get("/api/v2/users")
async def api_v2_users(_=Depends(verify_credentials)):
    """List all users."""
    return get_demo_users()


@router.post("/api/v2/users")
async def api_v2_users_create(body: dict, _=Depends(verify_credentials)):
    """Create a new user."""
    username = body.get("username")
    role = body.get("role", "viewer")
    email = body.get("email", "")

    if not username:
        raise HTTPException(status_code=400, detail="Username required")

    return add_demo_user(username, role, email)


@router.put("/api/v2/users/{user_id}")
async def api_v2_users_update(user_id: str, body: dict, _=Depends(verify_credentials)):
    """Update a user."""
    user = update_demo_user(user_id, body)
    if user:
        return user
    raise HTTPException(status_code=404, detail="User not found")


@router.delete("/api/v2/users/{user_id}")
async def api_v2_users_delete(user_id: str, _=Depends(verify_credentials)):
    """Delete a user."""
    success = delete_demo_user(user_id)
    return {"success": success}
