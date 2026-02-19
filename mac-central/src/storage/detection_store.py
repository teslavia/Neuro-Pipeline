"""SQLite-based detection event storage with retry on lock.

Facade that delegates to domain-specific repo modules:
  _detection_repo  — detection CRUD
  _timeseries_repo — time-series CRUD
  _conversation_repo — conversation CRUD
"""

import asyncio
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.storage import _conversation_repo, _detection_repo, _timeseries_repo

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

CREATE TABLE IF NOT EXISTS timeseries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    device_id TEXT NOT NULL DEFAULT '',
    metric_name TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ts_device_metric_ts ON timeseries(device_id, metric_name, timestamp);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    context_type TEXT DEFAULT 'vlm'
);
CREATE INDEX IF NOT EXISTS idx_conv_device_ts ON conversations(device_id, timestamp);
"""


class DetectionStore:
    """Thread-safe SQLite store — thin facade over domain repos."""

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
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_detections_device_ts ON detections(device_id, timestamp)"
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

    # --- Detections (delegated) ---

    def record(self, event: dict) -> None:
        _detection_repo.record(self._conn, self._lock, event)

    def query(
        self, since: float, until: float = 0, limit: int = 100, device_id: str = ""
    ) -> list[dict]:
        return _detection_repo.query(self._conn, self._lock, since, until, limit, device_id)

    def cleanup(self) -> int:
        return _detection_repo.cleanup(self._conn, self._lock, self.retention_days)

    def count(self) -> int:
        return _detection_repo.count(self._conn, self._lock)

    # --- Time Series (delegated) ---

    def record_timeseries(self, device_id: str, metric_name: str, value: float,
                          timestamp: float = 0) -> None:
        _timeseries_repo.record(self._conn, self._lock, device_id, metric_name, value, timestamp)

    def query_timeseries(self, metric_name: str, device_id: str = "",
                         start_time: float = 0, end_time: float = 0,
                         aggregation: str = "avg", bucket_seconds: int = 0,
                         limit: int = 1000) -> list[dict]:
        return _timeseries_repo.query(
            self._conn, self._lock, metric_name, device_id,
            start_time, end_time, aggregation, bucket_seconds, limit,
        )

    # --- Conversations (delegated) ---

    def record_conversation(self, device_id: str, role: str, content: str,
                            context_type: str = "vlm", timestamp: float = 0) -> None:
        _conversation_repo.record(self._conn, self._lock, device_id, role, content, context_type, timestamp)

    def query_conversations(self, device_id: str, limit: int = 20,
                            context_type: str = "", since: float = 0) -> list[dict]:
        return _conversation_repo.query(self._conn, self._lock, device_id, limit, context_type, since)

    # --- Lifecycle ---

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
