"""RAG retriever for historical detection context.

Queries SQLite detection history to provide VLM with relevant
past events as context for more informed analysis.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """Retrieved context for VLM augmentation."""
    items: list[dict]
    summary: str
    query_time_ms: float


class RAGRetriever:
    """Retrieves historical detection events as VLM context."""

    def __init__(
        self,
        detection_store=None,
        max_items: int = 10,
        time_window_hours: float = 24.0,
    ) -> None:
        self._store = detection_store
        self._max_items = max_items
        self._time_window_hours = time_window_hours

    def retrieve(
        self,
        device_id: str,
        class_names: list[str] | None = None,
        time_window_hours: float = 0,
    ) -> RAGContext:
        """Retrieve relevant historical events for a device.

        Args:
            device_id: Edge device to query history for.
            class_names: Filter by detection class names (optional).
            time_window_hours: Override default time window (0 = use default).

        Returns:
            RAGContext with matched items and formatted summary.
        """
        if not self._store:
            return RAGContext(items=[], summary="No history available.", query_time_ms=0)

        t0 = time.perf_counter()
        window = time_window_hours or self._time_window_hours
        since = time.time() - window * 3600

        rows = self._store.query(
            since=since, limit=self._max_items * 3, device_id=device_id
        )

        # Filter by class names if specified
        if class_names:
            filtered = []
            for row in rows:
                dets = row.get("detections", [])
                if any(d.get("class_name") in class_names for d in dets):
                    filtered.append(row)
            rows = filtered

        items = rows[: self._max_items]
        elapsed = (time.perf_counter() - t0) * 1000

        summary = self._format_summary(items, device_id, window)
        return RAGContext(items=items, summary=summary, query_time_ms=elapsed)

    def _format_summary(self, items: list[dict], device_id: str, hours: float) -> str:
        """Format retrieved items into a text summary for VLM prompt."""
        if not items:
            return f"No recent events for device {device_id} in the last {hours:.0f}h."

        lines = [f"Recent history for {device_id} ({len(items)} events, last {hours:.0f}h):"]
        for item in items:
            ts = item.get("timestamp", 0)
            event_type = item.get("event_type", item.get("type", "detection"))
            dets = item.get("detections", [])
            classes = [d.get("class_name", "?") for d in dets]
            vlm = item.get("vlm_result", "")

            time_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "?"
            det_str = ", ".join(classes) if classes else "none"
            line = f"  [{time_str}] {event_type}: {det_str}"
            if vlm:
                line += f" — VLM: {vlm[:80]}"
            lines.append(line)

        return "\n".join(lines)

    def format_for_prompt(self, context: RAGContext) -> str:
        """Format RAG context for injection into a prompt template."""
        return context.summary
