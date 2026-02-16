"""SQLite-based detection event storage with retry on lock."""

import asyncio
import json
import logging
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.observability.retry import retry_sync

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
    rule_matched TEXT,
    device_id TEXT DEFAULT ''
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
        self._migrate()
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_detections_device ON detections(device_id)"
        )
        self._conn.commit()
        logger.info(f"DetectionStore opened: {self.db_path}")

    def _migrate(self) -> None:
        """Add device_id column to legacy databases that lack it."""
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(detections)").fetchall()
        }
        if "device_id" not in cols:
            self._conn.execute(
                "ALTER TABLE detections ADD COLUMN device_id TEXT DEFAULT ''"
            )
            self._conn.commit()
            logger.info("Migrated: added device_id column")

    def record(self, event: dict) -> None:
        """Insert a detection event (retries on SQLite lock)."""
        def _do_insert():
            with self._lock:
                self._conn.execute(
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
                self._conn.commit()
        retry_sync(_do_insert, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))

    def query(
        self, since: float, until: float = 0, limit: int = 100, device_id: str = ""
    ) -> list[dict]:
        """Query events in a time range, optionally filtered by device_id."""
        if until <= 0:
            until = time.time()
        def _do_query():
            with self._lock:
                if device_id:
                    rows = self._conn.execute(
                        "SELECT * FROM detections WHERE timestamp >= ? AND timestamp <= ? "
                        "AND device_id = ? ORDER BY timestamp DESC LIMIT ?",
                        (since, until, device_id, limit),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM detections WHERE timestamp >= ? AND timestamp <= ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (since, until, limit),
                    ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        return retry_sync(_do_query, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))

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

    def backup(self, dest_path: Path) -> bool:
        """Create an atomic backup using sqlite3.backup(). Returns True on success."""
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock:
                if not self._conn:
                    return False
                dest_conn = sqlite3.connect(str(dest_path))
                self._conn.backup(dest_conn)
                dest_conn.close()
            logger.info(f"Backup created: {dest_path}")
            return True
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Backup failed: {e}")
            return False

    async def schedule_backup(
        self, backup_dir: Path, interval_hours: float = 24.0
    ) -> None:
        """Periodically backup the database. Runs as an async task."""
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        while True:
            await asyncio.sleep(interval_hours * 3600)
            date_str = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = backup_dir / f"detections-{date_str}.db"
            self.backup(dest)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("detections_json"):
            d["detections"] = json.loads(d.pop("detections_json"))
        else:
            d.pop("detections_json", None)
            d["detections"] = []
        return d
