"""Internal: conversation CRUD operations."""

import sqlite3
import threading
import time

from src.observability.retry import retry_sync


def record(
    conn: sqlite3.Connection, lock: threading.Lock,
    device_id: str, role: str, content: str,
    context_type: str = "vlm", timestamp: float = 0,
) -> None:
    """Record a conversation turn (for multi-round reasoning)."""
    ts = timestamp or time.time()

    def _do():
        with lock:
            conn.execute(
                "INSERT INTO conversations (device_id, timestamp, role, content, context_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (device_id, ts, role, content, context_type),
            )
            conn.commit()
    retry_sync(_do, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))


def query(
    conn: sqlite3.Connection, lock: threading.Lock,
    device_id: str, limit: int = 20,
    context_type: str = "", since: float = 0,
) -> list[dict]:
    """Query conversation history for a device."""
    def _do():
        with lock:
            sql = "SELECT device_id, timestamp, role, content, context_type FROM conversations WHERE device_id = ? "
            params: list = [device_id]
            if context_type:
                sql += "AND context_type = ? "
                params.append(context_type)
            if since > 0:
                sql += "AND timestamp >= ? "
                params.append(since)
            sql += "ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [
                {"device_id": r[0], "timestamp": r[1], "role": r[2],
                 "content": r[3], "context_type": r[4]}
                for r in rows
            ][::-1]  # reverse to chronological order
    return retry_sync(_do, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))
