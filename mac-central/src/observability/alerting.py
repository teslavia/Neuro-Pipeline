"""Simple alerting — CRITICAL log + optional webhook POST with severity routing."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRoute:
    severity: AlertSeverity = AlertSeverity.CRITICAL
    webhook_url: str = ""


@dataclass
class AlertRule:
    name: str
    cooldown_seconds: float = 300.0
    severity: AlertSeverity = AlertSeverity.CRITICAL


class AlertManager:
    """Fire alerts via logging and optional webhook with severity routing."""

    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        webhook_url: str = "",
        enabled: bool = True,
        routes: Optional[List[AlertRoute]] = None,
    ):
        self.rules: Dict[str, AlertRule] = {r.name: r for r in (rules or [])}
        self.webhook_url = webhook_url
        self.enabled = enabled
        self._last_fired: Dict[str, float] = {}
        self._routes: Dict[AlertSeverity, str] = {}
        if routes:
            for route in routes:
                self._routes[route.severity] = route.webhook_url

    def _get_webhook_url(self, severity: AlertSeverity) -> str:
        """Get webhook URL for severity, falling back to default."""
        return self._routes.get(severity, self.webhook_url)

    async def check_and_fire(self, event_type: str, context: dict) -> bool:
        """Check rule + cooldown, fire if appropriate. Returns True if fired."""
        if not self.enabled:
            return False
        rule = self.rules.get(event_type)
        if rule is None:
            return False

        now = time.monotonic()
        if event_type in self._last_fired and now - self._last_fired[event_type] < rule.cooldown_seconds:
            return False

        self._last_fired[event_type] = now
        severity = getattr(rule, 'severity', AlertSeverity.CRITICAL)

        if severity == AlertSeverity.CRITICAL:
            logger.critical(f"ALERT [{event_type}]: {context}")
        elif severity == AlertSeverity.WARNING:
            logger.warning(f"ALERT [{event_type}]: {context}")
        else:
            logger.info(f"ALERT [{event_type}]: {context}")

        url = self._get_webhook_url(severity)
        if url:
            await self._post_webhook(url, event_type, context)
        return True

    async def _post_webhook(self, url: str, event_type: str, context: dict) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    url,
                    json={"alert": event_type, "context": context},
                )
        except (OSError, ConnectionError) as e:
            logger.error(f"Webhook POST failed: {e}")
