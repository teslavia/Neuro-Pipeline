"""SQLite-based detection event storage."""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    frame_id INTEGER,
    trace_id TEXT,
    event_type TEXT NOT NULL,
    detections_json TEXT,
    vlm_result TEXT,
    rule_matched TEXT
);
CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(timestamp);
"""


class DetectionStore:
    """Thread-safe SQLite store for detection events."""

    def __init__(self, db_path: Path, retention_days: int = 7) -> None:
        self.db_path = db_path
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        logger.info(f"DetectionStore opened: {self.db_path}")

    def record(self, event: dict) -> None:
        """Insert a detection event."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO detections "
                "(timestamp, frame_id, trace_id, event_type, detections_json, vlm_result, rule_matched) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.get("timestamp", time.time()),
                    event.get("frame_id"),
                    event.get("trace_id"),
                    event.get("type", "detection"),
                    json.dumps(event.get("detections", [])),
                    event.get("vlm_result"),
                    event.get("rule"),
                ),
            )
            self._conn.commit()

    def query(
        self, since: float, until: float = 0, limit: int = 100
    ) -> list[dict]:
        """Query events in a time range. until=0 means now."""
        if until <= 0:
            until = time.time()
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM detections WHERE timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (since, until, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def cleanup(self) -> int:
        """Delete events older than retention_days. Returns count deleted."""
        cutoff = time.time() - self.retention_days * 86400
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM detections WHERE timestamp < ?", (cutoff,)
            )
            self._conn.commit()
            logger.info(f"Cleaned up {cur.rowcount} old events")
            return cur.rowcount

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM detections").fetchone()
            return row[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("DetectionStore closed")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("detections_json"):
            d["detections"] = json.loads(d.pop("detections_json"))
        else:
            d.pop("detections_json", None)
            d["detections"] = []
        return d
