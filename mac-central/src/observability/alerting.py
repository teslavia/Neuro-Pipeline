"""Simple alerting — CRITICAL log + optional webhook POST."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    name: str
    cooldown_seconds: float = 300.0


class AlertManager:
    """Fire alerts via logging and optional webhook."""

    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        webhook_url: str = "",
        enabled: bool = True,
    ):
        self.rules: Dict[str, AlertRule] = {r.name: r for r in (rules or [])}
        self.webhook_url = webhook_url
        self.enabled = enabled
        self._last_fired: Dict[str, float] = {}

    async def check_and_fire(self, event_type: str, context: dict) -> bool:
        """Check rule + cooldown, fire if appropriate. Returns True if fired."""
        if not self.enabled:
            return False
        rule = self.rules.get(event_type)
        if rule is None:
            return False

        now = time.monotonic()
        last = self._last_fired.get(event_type, 0.0)
        if now - last < rule.cooldown_seconds:
            return False

        self._last_fired[event_type] = now
        logger.critical(f"ALERT [{event_type}]: {context}")

        if self.webhook_url:
            await self._post_webhook(event_type, context)
        return True

    async def _post_webhook(self, event_type: str, context: dict) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    self.webhook_url,
                    json={"alert": event_type, "context": context},
                )
        except Exception as e:
            logger.error(f"Webhook POST failed: {e}")
