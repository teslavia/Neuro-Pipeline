"""Tests for Dashboard HTTP Basic Auth."""

import os
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

# Add repo root so extensions.dashboard can be found
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extensions.dashboard.app import app


@pytest.fixture(autouse=True)
def _set_auth_env(monkeypatch):
    """Set dashboard auth credentials for all tests."""
    monkeypatch.setenv("DASHBOARD_USER", "admin")
    monkeypatch.setenv("DASHBOARD_PASS", "secret123")


@pytest.mark.asyncio
async def test_valid_credentials():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status", auth=("admin", "secret123"))
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_credentials_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status", auth=("admin", "wrong"))
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_credentials_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_healthz_no_auth_required():
    """Healthz should be accessible without credentials."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
