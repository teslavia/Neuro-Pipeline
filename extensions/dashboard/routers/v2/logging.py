"""V2 API routes for dynamic log level management."""

import logging

from fastapi import HTTPException
from fastapi.routing import APIRouter

router = APIRouter(tags=["v2-logging"])

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@router.get("/api/v2/logging/level")
async def get_log_level():
    """Get current root logger level."""
    return {"level": logging.getLevelName(logging.getLogger().level).lower()}


@router.put("/api/v2/logging/level")
async def set_log_level(body: dict):
    """Set root logger level dynamically."""
    level_str = body.get("level", "").upper()
    if level_str not in _VALID_LEVELS:
        raise HTTPException(400, f"Invalid level: {level_str}. Must be one of {sorted(_VALID_LEVELS)}")

    level = getattr(logging, level_str)
    logging.getLogger().setLevel(level)
    # Propagate to loggers without custom handlers
    for name in list(logging.root.manager.loggerDict):
        lg = logging.getLogger(name)
        if not lg.handlers:
            lg.setLevel(level)

    return {"level": level_str.lower()}
