"""Tests for alerting wiring — log-only alerts, severity routing, cooldown."""

import asyncio
import logging
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from observability.alerting import AlertManager, AlertRule, AlertSeverity, AlertRoute


@pytest.mark.asyncio
async def test_log_only_alert_fires_without_webhook():
    """AlertManager with no webhook should still fire log-only alerts."""
    mgr = AlertManager(
        rules=[AlertRule(name="test_event", cooldown_seconds=0)],
        webhook_url="",
    )
    fired = await mgr.check_and_fire("test_event", {"detail": "test"})
    assert fired is True


@pytest.mark.asyncio
async def test_severity_routing():
    """Alerts should route to the correct webhook based on severity."""
    mgr = AlertManager(
        rules=[
            AlertRule(name="warn_event", cooldown_seconds=0, severity=AlertSeverity.WARNING),
            AlertRule(name="crit_event", cooldown_seconds=0, severity=AlertSeverity.CRITICAL),
        ],
        webhook_url="",
        routes=[
            AlertRoute(severity=AlertSeverity.WARNING, webhook_url="http://warn.example.com"),
            AlertRoute(severity=AlertSeverity.CRITICAL, webhook_url="http://crit.example.com"),
        ],
    )
    # Verify routing resolves correctly
    assert mgr._get_webhook_url(AlertSeverity.WARNING) == "http://warn.example.com"
    assert mgr._get_webhook_url(AlertSeverity.CRITICAL) == "http://crit.example.com"
    assert mgr._get_webhook_url(AlertSeverity.INFO) == ""  # Falls back to default


@pytest.mark.asyncio
async def test_cooldown_prevents_rapid_fire():
    """Cooldown should prevent the same alert from firing too quickly."""
    mgr = AlertManager(
        rules=[AlertRule(name="cd_event", cooldown_seconds=999)],
        webhook_url="",
    )
    first = await mgr.check_and_fire("cd_event", {})
    second = await mgr.check_and_fire("cd_event", {})
    assert first is True
    assert second is False
