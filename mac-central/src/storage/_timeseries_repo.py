"""Internal: time-series CRUD operations."""

import sqlite3
import threading
import time

from src.observability.retry import retry_sync


def record(
    conn: sqlite3.Connection, lock: threading.Lock,
    device_id: str, metric_name: str, value: float, timestamp: float = 0,
) -> None:
    """Record a time-series data point."""
    ts = timestamp or time.time()

    def _do():
        with lock:
            conn.execute(
                "INSERT INTO timeseries (timestamp, device_id, metric_name, value) "
                "VALUES (?, ?, ?, ?)",
                (ts, device_id, metric_name, value),
            )
            conn.commit()
    retry_sync(_do, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))


def query(
    conn: sqlite3.Connection, lock: threading.Lock,
    metric_name: str, device_id: str = "",
    start_time: float = 0, end_time: float = 0,
    aggregation: str = "avg", bucket_seconds: int = 0,
    limit: int = 1000,
) -> list[dict]:
    """Query time-series data with optional aggregation."""
    if end_time <= 0:
        end_time = time.time()
    if start_time <= 0:
        start_time = end_time - 86400

    def _do():
        with lock:
            if bucket_seconds > 0:
                agg_fn = {"avg": "AVG", "sum": "SUM", "max": "MAX",
                          "min": "MIN", "count": "COUNT"}.get(aggregation, "AVG")
                sql = (
                    f"SELECT CAST(timestamp / ? AS INTEGER) * ? AS bucket_ts, "
                    f"{agg_fn}(value) AS agg_value "
                    f"FROM timeseries WHERE metric_name = ? AND timestamp >= ? AND timestamp <= ? "
                )
                params: list = [bucket_seconds, bucket_seconds, metric_name, start_time, end_time]
                if device_id:
                    sql += "AND device_id = ? "
                    params.append(device_id)
                sql += "GROUP BY bucket_ts ORDER BY bucket_ts LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
                return [{"timestamp": r[0], "value": r[1], "labels": {}} for r in rows]
            else:
                sql = (
                    "SELECT timestamp, value FROM timeseries "
                    "WHERE metric_name = ? AND timestamp >= ? AND timestamp <= ? "
                )
                params = [metric_name, start_time, end_time]
                if device_id:
                    sql += "AND device_id = ? "
                    params.append(device_id)
                sql += "ORDER BY timestamp LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
                return [{"timestamp": r[0], "value": r[1], "labels": {}} for r in rows]
    return retry_sync(_do, max_retries=3, backoff=0.1, exceptions=(sqlite3.OperationalError,))
