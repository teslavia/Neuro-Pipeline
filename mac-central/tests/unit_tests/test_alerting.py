"""Tests for alerting manager."""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.observability.alerting import AlertManager, AlertRule


@pytest.fixture
def alert_mgr():
    rules = [
        AlertRule(name="circuit_breaker_open", cooldown_seconds=0.2),
        AlertRule(name="edge_disconnect", cooldown_seconds=0.1),
        AlertRule(name="anomaly_detection", cooldown_seconds=0.05),
    ]
    return AlertManager(rules=rules, webhook_url="", enabled=True)


@pytest.mark.asyncio
async def test_alert_fires(alert_mgr, caplog):
    with caplog.at_level(logging.CRITICAL):
        fired = await alert_mgr.check_and_fire("circuit_breaker_open", {"reason": "test"})
    assert fired is True
    assert "circuit_breaker_open" in caplog.text


@pytest.mark.asyncio
async def test_cooldown_prevents_repeat(alert_mgr):
    await alert_mgr.check_and_fire("edge_disconnect", {})
    fired = await alert_mgr.check_and_fire("edge_disconnect", {})
    assert fired is False


@pytest.mark.asyncio
async def test_cooldown_expires(alert_mgr):
    await alert_mgr.check_and_fire("anomaly_detection", {})
    await asyncio.sleep(0.06)
    fired = await alert_mgr.check_and_fire("anomaly_detection", {})
    assert fired is True


@pytest.mark.asyncio
async def test_unknown_event_not_fired(alert_mgr):
    fired = await alert_mgr.check_and_fire("unknown_event", {})
    assert fired is False


@pytest.mark.asyncio
async def test_disabled_manager():
    mgr = AlertManager(rules=[AlertRule(name="x")], enabled=False)
    fired = await mgr.check_and_fire("x", {})
    assert fired is False


@pytest.mark.asyncio
async def test_webhook_post():
    rules = [AlertRule(name="test_alert", cooldown_seconds=0)]
    mgr = AlertManager(rules=rules, webhook_url="http://localhost:9999/hook")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock()

    with patch("src.observability.alerting.httpx", create=True) as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        # Re-import to pick up the mock — or just call directly
        fired = await mgr.check_and_fire("test_alert", {"key": "val"})

    assert fired is True


@pytest.mark.asyncio
async def test_no_webhook_only_logs(alert_mgr, caplog):
    """Without webhook_url, only logs are written."""
    with caplog.at_level(logging.CRITICAL):
        await alert_mgr.check_and_fire("circuit_breaker_open", {"info": "test"})
    assert "ALERT" in caplog.text
