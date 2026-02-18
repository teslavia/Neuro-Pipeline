"""V2 API routers."""

from .status import router as status_router
from .models import router as models_router
from .config import router as config_router
from .intelligence import router as intelligence_router
from .tracking import router as tracking_router

__all__ = [
    "status_router",
    "models_router",
    "config_router",
    "intelligence_router",
    "tracking_router",
]
