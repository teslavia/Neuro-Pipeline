"""Internal: detection event CRUD operations."""

import json
import sqlite3
import threading
import time

from src.observability.retry import retry_sync


def record(conn: sqlite3.Connection, lock: threading.Lock, event: dict) -> None:
    """Insert a detection event (retries on SQLite lock)."""
    def _do_insert():
        with lock:
            conn.execute(
                "INSERT INTO detections "
                "(timestamp, frame_id, trace_id, event_type, detections_json, vlm_result, rule_matched, device_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.get("timestamp", time.time()),
                    event.get("frame_id"),
                    event.get("trace_id"),
                    event.get("type", "detection"),
                    json.dumps(event.get("detections", [])),
                    event.get("vlm_result"),
                    event.get("rule"),
                    event.get("device_id", ""),
                ),
            )
            conn.commit()
    retry_sync(_do_insert, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))


def query(
    conn: sqlite3.Connection, lock: threading.Lock,
    since: float, until: float, limit: int, device_id: str,
) -> list[dict]:
    """Query events in a time range, optionally filtered by device_id."""
    if until <= 0:
        until = time.time()

    def _do_query():
        with lock:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM detections WHERE timestamp >= ? AND timestamp <= ? "
                    "AND device_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (since, until, device_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM detections WHERE timestamp >= ? AND timestamp <= ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (since, until, limit),
                ).fetchall()
        return [row_to_dict(r) for r in rows]
    return retry_sync(_do_query, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))


def cleanup(conn: sqlite3.Connection, lock: threading.Lock, retention_days: int) -> int:
    """Delete events older than retention_days. Returns count deleted."""
    cutoff = time.time() - retention_days * 86400
    with lock:
        cur = conn.execute("DELETE FROM detections WHERE timestamp < ?", (cutoff,))
        conn.commit()
        return cur.rowcount


def count(conn: sqlite3.Connection, lock: threading.Lock) -> int:
    with lock:
        row = conn.execute("SELECT COUNT(*) FROM detections").fetchone()
        return row[0]


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("detections_json"):
        d["detections"] = json.loads(d.pop("detections_json"))
    else:
        d.pop("detections_json", None)
        d["detections"] = []
    return d
