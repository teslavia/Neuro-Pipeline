"""Tests for dynamic log level endpoint."""

import logging

import pytest
from fastapi.testclient import TestClient

from extensions.dashboard.app import app

client = TestClient(app)


class TestLoggingEndpoint:
    def setup_method(self):
        """Reset root logger to INFO before each test."""
        logging.getLogger().setLevel(logging.INFO)

    def test_get_log_level(self):
        resp = client.get("/api/v2/logging/level")
        assert resp.status_code == 200
        assert resp.json()["level"] == "info"

    def test_set_log_level_debug(self):
        resp = client.put("/api/v2/logging/level", json={"level": "debug"})
        assert resp.status_code == 200
        assert resp.json()["level"] == "debug"
        assert logging.getLogger().level == logging.DEBUG

    def test_set_log_level_warning(self):
        resp = client.put("/api/v2/logging/level", json={"level": "WARNING"})
        assert resp.status_code == 200
        assert resp.json()["level"] == "warning"

    def test_set_invalid_level_returns_400(self):
        resp = client.put("/api/v2/logging/level", json={"level": "verbose"})
        assert resp.status_code == 400
        assert "Invalid level" in resp.json()["detail"]

    def test_set_empty_level_returns_400(self):
        resp = client.put("/api/v2/logging/level", json={"level": ""})
        assert resp.status_code == 400

    def test_roundtrip(self):
        """Set level then verify GET returns the new level."""
        client.put("/api/v2/logging/level", json={"level": "error"})
        resp = client.get("/api/v2/logging/level")
        assert resp.json()["level"] == "error"
