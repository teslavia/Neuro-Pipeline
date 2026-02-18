"""Event bus for Neuro-Pipeline.

Provides a publish-subscribe event system for decoupled communication
between components.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A system event."""
    type: str
    data: Dict[str, Any]
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"{self.type}-{int(self.timestamp * 1000)}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
        }


# Event type constants
class EventType:
    """Standard event types in Neuro-Pipeline."""

    # Detection events
    DETECTION_RECEIVED = "detection.received"
    DETECTION_PROCESSED = "detection.processed"
    DETECTION_FILTERED = "detection.filtered"

    # VLM events
    VLM_ANALYSIS_STARTED = "vlm.analysis.started"
    VLM_ANALYSIS_COMPLETED = "vlm.analysis.completed"
    VLM_ANALYSIS_ERROR = "vlm.analysis.error"

    # Device events
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    DEVICE_HEARTBEAT = "device.heartbeat"
    DEVICE_ERROR = "device.error"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # Alert events
    ALERT_TRIGGERED = "alert.triggered"
    ALERT_RESOLVED = "alert.resolved"

    # Model events
    MODEL_SWITCHED = "model.switched"
    MODEL_ERROR = "model.error"

    # Anomaly events
    ANOMALY_DETECTED = "anomaly.detected"
    BEHAVIOR_ALERT = "behavior.alert"

    # ReID events
    REID_MATCH = "reid.match"
    REID_TRACK_CREATED = "reid.track_created"


# Handler type
EventHandler = Callable[[Event], None]


class EventBus:
    """Publish-subscribe event bus for inter-component communication.

    Supports synchronous and async handlers, event filtering,
    and event history.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._async_subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._wildcard_subscribers: Set[EventHandler] = set()
        self._wildcard_async_subscribers: Set[Callable[[Event], Any]] = set()
        self._history: List[Event] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> Callable[[], None]:
        """Subscribe to events of a specific type.

        Args:
            event_type: Event type to subscribe to (or "*" for all events)
            handler: Sync function to call when event is published

        Returns:
            Unsubscribe function
        """
        if event_type == "*":
            self._wildcard_subscribers.add(handler)
            return lambda: self._wildcard_subscribers.discard(handler)

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

        def unsubscribe():
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass

        return unsubscribe

    def subscribe_async(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
    ) -> Callable[[], None]:
        """Subscribe to events with an async handler.

        Args:
            event_type: Event type to subscribe to (or "*" for all events)
            handler: Async function to call when event is published

        Returns:
            Unsubscribe function
        """
        if event_type == "*":
            self._wildcard_async_subscribers.add(handler)
            return lambda: self._wildcard_async_subscribers.discard(handler)

        if event_type not in self._async_subscribers:
            self._async_subscribers[event_type] = []
        self._async_subscribers[event_type].append(handler)

        def unsubscribe():
            if event_type in self._async_subscribers:
                try:
                    self._async_subscribers[event_type].remove(handler)
                except ValueError:
                    pass

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Publish an event synchronously.

        Calls sync handlers immediately. Async handlers are scheduled
        but not awaited.

        Args:
            event: Event to publish
        """
        # Add to history
        self._add_to_history(event)

        # Log significant events
        if event.type.startswith(("alert.", "anomaly.", "error.", "system.")):
            logger.info(f"Event: {event.type} from {event.source}")

        # Call sync handlers
        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Event handler error for {event.type}: {e}")

        # Call wildcard sync handlers
        for handler in self._wildcard_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Wildcard handler error: {e}")

        # Schedule async handlers (fire-and-forget)
        async_handlers = self._async_subscribers.get(event.type, [])
        for handler in async_handlers:
            try:
                asyncio.create_task(self._call_async_handler(handler, event))
            except Exception as e:
                logger.warning(f"Failed to schedule async handler: {e}")

        # Schedule wildcard async handlers
        for handler in self._wildcard_async_subscribers:
            try:
                asyncio.create_task(self._call_async_handler(handler, event))
            except Exception as e:
                logger.warning(f"Failed to schedule wildcard async handler: {e}")

    async def publish_async(self, event: Event) -> None:
        """Publish an event and await all handlers.

        Args:
            event: Event to publish
        """
        # Add to history
        self._add_to_history(event)

        # Log significant events
        if event.type.startswith(("alert.", "anomaly.", "error.", "system.")):
            logger.info(f"Event: {event.type} from {event.source}")

        # Call sync handlers
        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Event handler error for {event.type}: {e}")

        # Call wildcard sync handlers
        for handler in self._wildcard_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Wildcard handler error: {e}")

        # Call and await async handlers
        async_handlers = self._async_subscribers.get(event.type, [])
        for handler in async_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.warning(f"Async handler error for {event.type}: {e}")

        # Call and await wildcard async handlers
        for handler in self._wildcard_async_subscribers:
            try:
                await handler(event)
            except Exception as e:
                logger.warning(f"Wildcard async handler error: {e}")

    async def _call_async_handler(
        self,
        handler: Callable[[Event], Any],
        event: Event,
    ) -> None:
        """Call an async handler with error handling."""
        try:
            await handler(event)
        except Exception as e:
            logger.warning(f"Async handler error for {event.type}: {e}")

    def _add_to_history(self, event: Event) -> None:
        """Add event to history buffer."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Get recent events from history.

        Args:
            event_type: Filter by event type (optional)
            source: Filter by source (optional)
            limit: Maximum number of events to return

        Returns:
            List of matching events (newest first)
        """
        events = list(reversed(self._history))

        if event_type:
            events = [e for e in events if e.type == event_type]
        if source:
            events = [e for e in events if e.source == source]

        return events[:limit]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        """Count subscribers.

        Args:
            event_type: Count for specific type, or all if None

        Returns:
            Number of subscribers
        """
        if event_type is None:
            total = (
                sum(len(h) for h in self._subscribers.values()) +
                sum(len(h) for h in self._async_subscribers.values()) +
                len(self._wildcard_subscribers) +
                len(self._wildcard_async_subscribers)
            )
            return total

        return (
            len(self._subscribers.get(event_type, [])) +
            len(self._async_subscribers.get(event_type, []))
        )


# Global event bus instance
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _bus
    _bus = None
