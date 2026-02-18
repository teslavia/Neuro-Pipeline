"""Neuro-Pipeline Dashboard extension.

This package provides a FastAPI-based dashboard for monitoring and managing
the Neuro-Pipeline system.

Key modules:
- app: Main FastAPI application entry point
- routers: API route handlers (v1 legacy + v2 modern)
- services: State management, demo data, validators
- middleware: Authentication and other middleware
- templates: Jinja2 templates for HTMX frontend

Usage:
    # Run standalone
    uvicorn extensions.dashboard.app:app --reload

    # Mount in central server
    from extensions.dashboard import app, inject_from_central
    inject_from_central(detection_store=store, orchestrator=orch, ...)
"""

from .app import app, inject_from_central, templates

__all__ = ["app", "inject_from_central", "templates"]
