"""Dashboard routers module."""

from .legacy import router as legacy_router
from .v2 import (
    status_router,
    models_router,
    config_router,
    intelligence_router,
    tracking_router,
    logging_router,
)

__all__ = [
    "legacy_router",
    "status_router",
    "models_router",
    "config_router",
    "intelligence_router",
    "tracking_router",
    "logging_router",
]
