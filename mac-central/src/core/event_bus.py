"""Event bus — extracted from CentralOrchestrator._record_event + subscribe/unsubscribe."""

import asyncio
import time
from collections import deque
from typing import Any, Dict, List

from src.core.logging import get_logger
from src.observability.metrics import events_stored

logger = get_logger(__name__)


class EventBus:
    """In-memory event buffer with SQLite persistence and listener notification."""

    def __init__(self, detection_store=None, maxlen: int = 100) -> None:
        self._recent_events: deque = deque(maxlen=maxlen)
        self._listeners: List[asyncio.Queue] = []
        self._detection_store = detection_store

    def publish(self, event: Dict[str, Any]) -> None:
        """Record event to buffer, persist to DB, and notify listeners."""
        self._recent_events.append(event)

        if self._detection_store:
            try:
                self._detection_store.record(event)
                events_stored.inc()
                # Write timeseries data points
                device_id = event.get("device_id", "")
                ts = event.get("timestamp", time.time())
                if event.get("type") == "detection" and event.get("detections"):
                    self._detection_store.record_timeseries(
                        device_id, "detections_count",
                        float(len(event["detections"])), ts
                    )
                if event.get("type") == "vlm_analysis":
                    self._detection_store.record_timeseries(
                        device_id, "vlm_analyses_count", 1.0, ts
                    )
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")

        for q in self._listeners:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to real-time event stream. Returns a queue that receives events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe from event stream."""
        if q in self._listeners:
            self._listeners.remove(q)

    def get_recent(self, limit: int = 50, device_id: str = "") -> List[Dict[str, Any]]:
        """Return recent events, optionally filtered by device_id."""
        events = list(self._recent_events)
        if device_id:
            events = [e for e in events if e.get("device_id") == device_id]
        return events[-limit:]
