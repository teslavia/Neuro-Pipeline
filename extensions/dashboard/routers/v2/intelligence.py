"""V2 API routes for behavior analysis, anomaly detection, and VLM guidance."""

from fastapi import APIRouter, Depends, Query

from ...middleware import verify_credentials
from ...services import (
    get_demo_behavior_events,
    get_demo_baselines,
    get_demo_anomaly_scores,
    get_demo_vlm_guidance,
)

router = APIRouter(tags=["v2-intelligence"])


# ── Behavior Analysis ──────────────────────────────────────

@router.get("/api/v2/behavior/events")
async def api_v2_behavior_events(
    device_id: str = "",
    behavior_type: str = "",
    limit: int = Query(50, ge=1, le=200),
    _=Depends(verify_credentials),
):
    """Query behavior analysis events."""
    return get_demo_behavior_events(device_id, behavior_type, limit)


# ── Anomaly Detection ──────────────────────────────────────

@router.get("/api/v2/anomaly/baselines")
async def api_v2_anomaly_baselines(_=Depends(verify_credentials)):
    """Get baseline statistics for anomaly detection."""
    return get_demo_baselines()


@router.get("/api/v2/anomaly/scores")
async def api_v2_anomaly_scores(
    device_id: str = "",
    hours: int = Query(24, ge=1, le=168),
    _=Depends(verify_credentials),
):
    """Query anomaly scores."""
    return get_demo_anomaly_scores(device_id, hours)


# ── VLM Guidance ──────────────────────────────────────

@router.get("/api/v2/vlm/guidance")
async def api_v2_vlm_guidance(device_id: str = "", _=Depends(verify_credentials)):
    """Get VLM configuration guidance suggestions."""
    return get_demo_vlm_guidance(device_id)


@router.post("/api/v2/vlm/guidance/{guidance_id}/apply")
async def api_v2_vlm_guidance_apply(guidance_id: str, _=Depends(verify_credentials)):
    """Apply a VLM guidance suggestion."""
    # In production, this would update the actual config
    return {"success": True, "message": f"Guidance {guidance_id} applied"}
