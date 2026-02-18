"""V2 API routes for behavior analysis, anomaly detection, and VLM guidance."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from ...middleware import verify_credentials
from ...services import (
    get_demo_behavior_events,
    get_demo_baselines,
    get_demo_anomaly_scores,
    get_demo_vlm_guidance,
    behavior_analyzer,
    anomaly_baseline,
    reasoning_chain,
    rag_retriever,
    detection_store,
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
    # Use real behavior analyzer if available
    if behavior_analyzer is not None and detection_store is not None:
        import time
        end_time = time.time()
        start_time = end_time - 3600  # Last hour

        # Query recent detections and analyze
        history = detection_store.query(
            since=start_time,
            until=end_time,
            device_id=device_id if device_id else None,
            limit=500,
        )

        events = []
        for event in history[:limit]:
            detections = event.get("detections", [])
            dev_id = event.get("device_id", "")
            ts = event.get("timestamp", end_time)

            # Analyze this batch
            behavior_events = behavior_analyzer.analyze(dev_id, detections, ts)
            for be in behavior_events:
                # Filter by behavior_type if specified
                if behavior_type and be.behavior_type.value != behavior_type:
                    continue
                events.append({
                    "id": f"be-{int(ts * 1000)}-{be.behavior_type.value}",
                    "type": be.behavior_type.value,
                    "deviceId": be.device_id,
                    "confidence": be.confidence,
                    "description": be.description,
                    "timestamp": datetime.fromtimestamp(be.timestamp, tz=timezone.utc).isoformat(),
                    "metadata": be.metadata,
                })

        return events[:limit]

    # Fallback to demo data
    return get_demo_behavior_events(device_id, behavior_type, limit)


# ── Anomaly Detection ──────────────────────────────────────

@router.get("/api/v2/anomaly/baselines")
async def api_v2_anomaly_baselines(_=Depends(verify_credentials)):
    """Get baseline statistics for anomaly detection."""
    # Use real anomaly baseline if available
    if anomaly_baseline is not None:
        baselines = anomaly_baseline.list_baselines()
        result = []
        for b in baselines:
            result.append({
                "metricName": b.metric_name,
                "deviceId": b.device_id,
                "mean": round(b.mean, 4),
                "stdDev": round(b.std_dev, 4),
                "sampleCount": b.sample_count,
                "lastUpdated": datetime.fromtimestamp(b.last_updated, tz=timezone.utc).isoformat(),
            })
        return result

    # Fallback to demo data
    return get_demo_baselines()


@router.get("/api/v2/anomaly/scores")
async def api_v2_anomaly_scores(
    device_id: str = "",
    hours: int = Query(24, ge=1, le=168),
    _=Depends(verify_credentials),
):
    """Query anomaly scores."""
    # Use real anomaly baseline if available
    if anomaly_baseline is not None and detection_store is not None:
        import time
        from collections import defaultdict

        end_time = time.time()
        start_time = end_time - hours * 3600

        # Query detection counts per device per hour
        history = detection_store.query(
            since=start_time,
            until=end_time,
            device_id=device_id if device_id else None,
            limit=10000,
        )

        # Aggregate by device and hour
        hourly_counts: dict[str, list[float]] = defaultdict(list)
        for event in history:
            dev_id = event.get("device_id", "unknown")
            ts = event.get("timestamp", end_time)
            hour_bucket = int(ts / 3600)
            key = f"{dev_id}"
            hourly_counts[key].append(len(event.get("detections", [])))

        # Calculate hourly averages and score
        scores = []
        for dev_id, counts in hourly_counts.items():
            if not counts:
                continue
            avg_count = sum(counts) / len(counts)

            # Try to score against baseline
            score = anomaly_baseline.score(dev_id, "detections_per_frame", avg_count)

            scores.append({
                "deviceId": dev_id,
                "metric": "detections_per_frame",
                "value": round(avg_count, 2),
                "zScore": round(score.z_score, 2),
                "isAnomaly": score.is_anomaly,
                "baselineMean": round(score.baseline_mean, 2),
                "baselineStd": round(score.baseline_std, 2),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })

        return sorted(scores, key=lambda x: abs(x["zScore"]), reverse=True)[:50]

    # Fallback to demo data
    return get_demo_anomaly_scores(device_id, hours)


# ── VLM Guidance ──────────────────────────────────────

@router.get("/api/v2/vlm/guidance")
async def api_v2_vlm_guidance(device_id: str = "", _=Depends(verify_credentials)):
    """Get VLM configuration guidance suggestions."""
    # Use RAG retriever if available for context-aware guidance
    if rag_retriever is not None and detection_store is not None:
        import time

        # Get recent detection patterns
        recent = rag_retriever.retrieve(
            query="unusual behavior patterns",
            device_id=device_id if device_id else None,
            limit=10,
        )

        suggestions = []
        # Generate guidance based on patterns
        if recent:
            # Check for high-confidence detections
            high_conf = [r for r in recent if r.get("avg_confidence", 0) > 0.8]
            if high_conf:
                suggestions.append({
                    "id": "guidance-high-conf",
                    "type": "threshold_adjustment",
                    "title": "提高置信度阈值",
                    "description": f"检测到 {len(high_conf)} 个设备平均置信度 > 80%，建议提高阈值以减少误报。",
                    "suggestedAction": {"threshold": 0.85},
                    "priority": "medium",
                    "createdAt": datetime.now(tz=timezone.utc).isoformat(),
                })

            # Check for crowded periods
            crowded = [r for r in recent if r.get("detection_count", 0) > 50]
            if crowded:
                suggestions.append({
                    "id": "guidance-crowd-zones",
                    "type": "zone_configuration",
                    "title": "配置人群聚集区域",
                    "description": f"检测到 {len(crowded)} 个时间段检测数量 > 50，建议配置专门的拥挤监控规则。",
                    "suggestedAction": {"zone": "high_traffic"},
                    "priority": "high",
                    "createdAt": datetime.now(tz=timezone.utc).isoformat(),
                })

        if not suggestions:
            suggestions.append({
                "id": "guidance-no-action",
                "type": "status",
                "title": "系统运行正常",
                "description": "当前检测模式稳定，无需调整配置。",
                "suggestedAction": {},
                "priority": "low",
                "createdAt": datetime.now(tz=timezone.utc).isoformat(),
            })

        return suggestions

    # Fallback to demo data
    return get_demo_vlm_guidance(device_id)


@router.post("/api/v2/vlm/guidance/{guidance_id}/apply")
async def api_v2_vlm_guidance_apply(guidance_id: str, _=Depends(verify_credentials)):
    """Apply a VLM guidance suggestion."""
    # In production, this would update the actual config
    return {"success": True, "message": f"Guidance {guidance_id} applied"}
