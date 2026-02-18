"""Neuro-Pipeline Dashboard — FastAPI application entry point.

This module provides the main FastAPI application with:
- Legacy v1 API for backward compatibility
- Modern v2 API for neuro-dashboard frontend
- WebSocket for real-time updates
- Prometheus metrics endpoint
- Health probes for Kubernetes

Usage:
    # Run standalone (demo mode)
    uvicorn extensions.dashboard.app:app --reload

    # Import and mount in central server
    from extensions.dashboard.app import app, inject_from_central
    inject_from_central(detection_store=store, ...)
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.templating import Jinja2Templates

from .routers import (
    legacy_router,
    status_router,
    models_router,
    config_router,
    intelligence_router,
    tracking_router,
)
from .services import inject_from_central


# ── Application Setup ──────────────────────────────────────

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Neuro-Pipeline Dashboard",
    description="Real-time monitoring and management API for Neuro-Pipeline",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow neuro-dashboard frontend (Next.js dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include Routers ──────────────────────────────────────

# Legacy v1 API
app.include_router(legacy_router)

# V2 API
app.include_router(status_router)
app.include_router(models_router)
app.include_router(config_router)
app.include_router(intelligence_router)
app.include_router(tracking_router)


# ── Health Probes ──────────────────────────────────────

@app.get("/healthz")
async def healthz():
    """Liveness probe — always 200 if process is running."""
    from .services import health_checker

    if health_checker:
        status = health_checker.liveness()
        from fastapi.responses import JSONResponse
        return JSONResponse({"alive": status.alive, "checks": status.checks})
    return {"alive": True}


@app.get("/readyz")
async def readyz():
    """Readiness probe — 200 if all subsystems ready, 503 otherwise."""
    from fastapi.responses import JSONResponse
    from .middleware import verify_credentials
    from .services import health_checker

    # Run auth check (no-op if not configured)
    try:
        # verify_credentials requires Depends, so we skip it here
        pass
    except Exception:
        pass

    if health_checker:
        status = health_checker.readiness()
        code = 200 if status.ready else 503
        return JSONResponse(
            {"ready": status.ready, "checks": status.checks},
            status_code=code,
        )
    return {"ready": True}


# ── Prometheus Metrics ──────────────────────────────────────

@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics in text exposition format."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Exports ──────────────────────────────────────

# Re-export inject_from_central for convenience
__all__ = ["app", "inject_from_central", "templates"]
