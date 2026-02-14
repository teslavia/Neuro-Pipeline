"""Tests for health check probes."""

import pytest
from unittest.mock import MagicMock

from src.observability.health import HealthChecker, HealthStatus


def test_liveness_always_true():
    checker = HealthChecker()
    status = checker.liveness()
    assert status.alive is True


def test_readiness_all_ready():
    orch = MagicMock()
    orch.inference_engine._loaded = True
    store = MagicMock()
    store._conn = MagicMock()
    server = MagicMock()
    server.server = MagicMock()

    checker = HealthChecker(orchestrator=orch, store=store, server=server)
    status = checker.readiness()
    assert status.ready is True
    assert status.checks["model_loaded"] is True
    assert status.checks["db_connected"] is True
    assert status.checks["grpc_serving"] is True


def test_readiness_model_not_loaded():
    orch = MagicMock()
    orch.inference_engine._loaded = False
    store = MagicMock()
    store._conn = MagicMock()
    server = MagicMock()
    server.server = MagicMock()

    checker = HealthChecker(orchestrator=orch, store=store, server=server)
    status = checker.readiness()
    assert status.ready is False
    assert status.checks["model_loaded"] is False


def test_readiness_no_db():
    orch = MagicMock()
    orch.inference_engine._loaded = True
    store = MagicMock()
    store._conn = None
    server = MagicMock()
    server.server = MagicMock()

    checker = HealthChecker(orchestrator=orch, store=store, server=server)
    status = checker.readiness()
    assert status.ready is False
    assert status.checks["db_connected"] is False


def test_readiness_no_grpc():
    orch = MagicMock()
    orch.inference_engine._loaded = True
    store = MagicMock()
    store._conn = MagicMock()
    server = MagicMock()
    server.server = None

    checker = HealthChecker(orchestrator=orch, store=store, server=server)
    status = checker.readiness()
    assert status.ready is False
    assert status.checks["grpc_serving"] is False


def test_readiness_none_components():
    checker = HealthChecker()
    status = checker.readiness()
    assert status.ready is False
