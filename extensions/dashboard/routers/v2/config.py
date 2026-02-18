"""V2 API routes for configuration management."""

import shutil
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
import yaml

from ...middleware import verify_credentials
from ...services import config_path, validate_config

router = APIRouter(tags=["v2-config"])


def _resolve_config_path() -> Path:
    """Resolve the config file path."""
    config_file = config_path or "config.yaml"
    path = Path(config_file)
    if not path.is_absolute():
        # Try relative to repo root (extensions/dashboard/../../../config.yaml)
        path = Path(__file__).parent.parent.parent.parent.parent / config_file
    return path


@router.get("/api/v2/config")
async def api_v2_config(_=Depends(verify_credentials)):
    """Get current configuration."""
    path = _resolve_config_path()

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f)

    return {
        "path": str(path),
        "config": config,
        "lastModified": path.stat().st_mtime,
    }


@router.put("/api/v2/config")
async def api_v2_config_update(body: dict, _=Depends(verify_credentials)):
    """Update configuration (with validation)."""
    path = _resolve_config_path()

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {path}")

    new_config = body.get("config")
    if new_config is None:
        raise HTTPException(status_code=400, detail="Missing config in body")

    # Validate
    errors = validate_config(new_config)
    if errors:
        return {"success": False, "errors": errors}

    # Backup existing config
    backup_path = path.with_suffix(".yaml.bak")
    if path.exists():
        shutil.copy(path, backup_path)

    try:
        with open(path, "w") as f:
            yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)
        return {"success": True, "message": "Config updated", "backupPath": str(backup_path)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/v2/config/dry-run")
async def api_v2_config_dry_run(body: dict, _=Depends(verify_credentials)):
    """Validate configuration without applying."""
    new_config = body.get("config")
    if new_config is None:
        raise HTTPException(status_code=400, detail="Missing config in body")

    errors = validate_config(new_config)
    return {"valid": len(errors) == 0, "errors": errors}
