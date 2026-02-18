"""V2 API routes for model management."""

import time

from fastapi import APIRouter, Depends, HTTPException

from ...middleware import verify_credentials
from ...services import (
    orchestrator,
    model_registry,
    ab_test_manager,
    get_demo_models,
)

router = APIRouter(tags=["v2-models"])


# ── Model Endpoints ──────────────────────────────────────

@router.get("/api/v2/models")
async def api_v2_models(device_id: str = "", _=Depends(verify_credentials)):
    """List all registered models."""
    if model_registry is None:
        return get_demo_models()

    models = model_registry.list_models(device_id=device_id)

    return [
        {
            "modelId": m.model_id,
            "modelPath": m.model_path,
            "modelType": m.model_type,
            "version": m.version,
            "status": m.status.value,
            "npuCore": m.npu_core,
            "deployedAt": m.deployed_at,
            "targetDeviceId": m.target_device_id,
            "metadata": m.metadata,
        }
        for m in models
    ]


@router.post("/api/v2/models/{model_id}/switch")
async def api_v2_models_switch(model_id: str, body: dict, _=Depends(verify_credentials)):
    """Switch active model variant on edge device."""
    device_id = body.get("device_id", "edge-001")

    if orchestrator is None:
        return {"success": False, "message": "Orchestrator not available"}

    try:
        from src.generated import neuro_pipeline_pb2
        cmd = neuro_pipeline_pb2.ControlCommand()
        cmd.type = neuro_pipeline_pb2.ControlCommand.CHANGE_MODEL
        cmd.command_id = int(time.time() * 1000)
        cmd.parameters["model_id"] = model_id
        cmd.parameters["device_id"] = device_id
        await orchestrator.send_command(cmd)
        return {"success": True, "message": f"Switch to {model_id} queued"}
    except ImportError:
        return {"success": False, "message": "Protobuf not available"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@router.post("/api/v2/models/reload")
async def api_v2_models_reload(body: dict = None, _=Depends(verify_credentials)):
    """Reload all models on edge device."""
    device_id = (body or {}).get("device_id", "edge-001")

    if orchestrator is None:
        return {"success": False, "message": "Orchestrator not available"}

    try:
        from src.generated import neuro_pipeline_pb2
        cmd = neuro_pipeline_pb2.ControlCommand()
        cmd.type = getattr(neuro_pipeline_pb2.ControlCommand, "RELOAD_MODEL", 6)
        cmd.command_id = int(time.time() * 1000)
        cmd.parameters["device_id"] = device_id
        await orchestrator.send_command(cmd)
        return {"success": True, "message": "Reload command queued"}
    except ImportError:
        return {"success": False, "message": "Protobuf not available"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@router.post("/api/v2/models/{model_id}/rollback")
async def api_v2_models_rollback(model_id: str, _=Depends(verify_credentials)):
    """Rollback model to previous version."""
    if model_registry is None:
        raise HTTPException(status_code=400, detail="Model registry not configured")

    success = model_registry.rollback(model_id)
    if success:
        return {"success": True, "message": f"Model {model_id} rolled back"}
    else:
        return {"success": False, "message": f"Cannot rollback {model_id}"}


# ── A/B Test Endpoints ──────────────────────────────────────

@router.get("/api/v2/ab-test")
async def api_v2_ab_test(_=Depends(verify_credentials)):
    """A/B test results endpoint."""
    if ab_test_manager is None:
        return {"enabled": False, "message": "A/B testing not configured"}

    result = ab_test_manager.evaluate()
    metrics = ab_test_manager.get_metrics()

    return {
        "enabled": True,
        "winner": result.winner,
        "confidence": result.confidence,
        "sufficient_samples": result.sufficient_samples,
        "variants": {
            name: {
                "total_inferences": m.total_inferences,
                "avg_latency_ms": round(m.avg_latency_ms, 2),
                "accuracy": round(m.accuracy, 4),
                "total_detections": m.total_detections,
            }
            for name, m in metrics.items()
        },
    }


@router.post("/api/v2/ab-test/split")
async def api_v2_ab_test_split(body: dict, _=Depends(verify_credentials)):
    """Adjust A/B test traffic split."""
    if ab_test_manager is None:
        raise HTTPException(status_code=400, detail="A/B testing not configured")

    new_split = body.get("traffic_split")
    if new_split is None or not (0.0 <= new_split <= 1.0):
        raise HTTPException(status_code=400, detail="traffic_split must be between 0 and 1")

    ab_test_manager._traffic_split = new_split
    return {"success": True, "traffic_split": new_split}


@router.post("/api/v2/ab-test/reset")
async def api_v2_ab_test_reset(_=Depends(verify_credentials)):
    """Reset A/B test metrics and group assignments."""
    if ab_test_manager is None:
        raise HTTPException(status_code=400, detail="A/B testing not configured")

    ab_test_manager.reset()
    return {"success": True}
