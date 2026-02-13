"""
Event handler for processing detection events from edge devices.
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EventHandler:
    """Handles detection events and triggers appropriate actions."""

    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.processing_task: Optional[asyncio.Task] = None
        logger.info("EventHandler initialized")

    async def start(self) -> None:
        """Start event processing loop."""
        self.processing_task = asyncio.create_task(self._process_events())
        logger.info("EventHandler started")

    async def stop(self) -> None:
        """Stop event processing loop."""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("EventHandler stopped")

    async def enqueue_detection(self, result: Any) -> None:
        """
        Enqueue detection result for processing.

        Args:
            result: DetectionResult protobuf message.
        """
        await self.event_queue.put(result)

    async def _process_events(self) -> None:
        """Background event processing loop."""
        logger.info("Event processing loop started")
        while True:
            try:
                result = await self.event_queue.get()
                await self.orchestrator.process_detection(result)
                self.event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")
