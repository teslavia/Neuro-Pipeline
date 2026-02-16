"""Tests for alert severity routing."""

import pytest
from unittest.mock import AsyncMock, patch

from src.observability.alerting import (
    AlertManager,
    AlertRoute,
    AlertRule,
    AlertSeverity,
)


class TestAlertSeverity:
    def test_severity_values(self):
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestAlertRouting:
    @pytest.mark.asyncio
    async def test_critical_uses_critical_route(self):
        routes = [
            AlertRoute(severity=AlertSeverity.CRITICAL, webhook_url="https://critical.hook"),
            AlertRoute(severity=AlertSeverity.WARNING, webhook_url="https://warning.hook"),
        ]
        rules = [AlertRule(name="test_event", cooldown_seconds=0, severity=AlertSeverity.CRITICAL)]
        mgr = AlertManager(rules=rules, routes=routes)

        with patch.object(mgr, '_post_webhook', new_callable=AsyncMock) as mock_post:
            await mgr.check_and_fire("test_event", {"key": "val"})
            mock_post.assert_awaited_once_with(
                "https://critical.hook", "test_event", {"key": "val"}
            )

    @pytest.mark.asyncio
    async def test_warning_uses_warning_route(self):
        routes = [
            AlertRoute(severity=AlertSeverity.CRITICAL, webhook_url="https://critical.hook"),
            AlertRoute(severity=AlertSeverity.WARNING, webhook_url="https://warning.hook"),
        ]
        rules = [AlertRule(name="warn_event", cooldown_seconds=0, severity=AlertSeverity.WARNING)]
        mgr = AlertManager(rules=rules, routes=routes)

        with patch.object(mgr, '_post_webhook', new_callable=AsyncMock) as mock_post:
            await mgr.check_and_fire("warn_event", {})
            mock_post.assert_awaited_once_with("https://warning.hook", "warn_event", {})

    @pytest.mark.asyncio
    async def test_fallback_to_default_webhook(self):
        rules = [AlertRule(name="test", cooldown_seconds=0, severity=AlertSeverity.CRITICAL)]
        mgr = AlertManager(rules=rules, webhook_url="https://default.hook")

        with patch.object(mgr, '_post_webhook', new_callable=AsyncMock) as mock_post:
            await mgr.check_and_fire("test", {})
            mock_post.assert_awaited_once_with("https://default.hook", "test", {})

    @pytest.mark.asyncio
    async def test_no_webhook_no_post(self):
        rules = [AlertRule(name="test", cooldown_seconds=0)]
        mgr = AlertManager(rules=rules)

        with patch.object(mgr, '_post_webhook', new_callable=AsyncMock) as mock_post:
            result = await mgr.check_and_fire("test", {})
            assert result is True
            mock_post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_info_severity_logs_info(self):
        rules = [AlertRule(name="info_event", cooldown_seconds=0, severity=AlertSeverity.INFO)]
        mgr = AlertManager(rules=rules)
        result = await mgr.check_and_fire("info_event", {"msg": "test"})
        assert result is True
