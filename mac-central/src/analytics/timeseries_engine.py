"""Time series analysis engine.

Provides trend detection, periodicity analysis, and anomaly point
detection on top of the timeseries data in DetectionStore.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TrendResult:
    """Result of trend analysis."""
    metric_name: str
    device_id: str
    direction: str  # "increasing", "decreasing", "stable"
    slope: float
    r_squared: float
    sample_count: int


@dataclass
class AnomalyPoint:
    """A detected anomaly point in the time series."""
    timestamp: float
    value: float
    expected: float
    deviation: float


class TimeSeriesEngine:
    """Analyzes time series data for trends, periodicity, and anomalies."""

    def __init__(self, detection_store=None) -> None:
        self._store = detection_store

    def detect_trend(
        self,
        device_id: str,
        metric_name: str,
        hours: float = 24.0,
    ) -> Optional[TrendResult]:
        """Detect trend direction using linear regression."""
        values = self._fetch_values(device_id, metric_name, hours)
        if len(values) < 3:
            return None

        n = len(values)
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(values) / n

        ss_xy = sum((xs[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        ss_xx = sum((xs[i] - x_mean) ** 2 for i in range(n))

        if ss_xx == 0:
            return TrendResult(
                metric_name=metric_name, device_id=device_id,
                direction="stable", slope=0.0, r_squared=0.0, sample_count=n,
            )

        slope = ss_xy / ss_xx
        intercept = y_mean - slope * x_mean

        # R-squared
        ss_res = sum((values[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return TrendResult(
            metric_name=metric_name, device_id=device_id,
            direction=direction, slope=slope, r_squared=r_squared,
            sample_count=n,
        )

    def detect_anomaly_points(
        self,
        device_id: str,
        metric_name: str,
        hours: float = 24.0,
        z_threshold: float = 3.0,
    ) -> list[AnomalyPoint]:
        """Find anomaly points using z-score on raw values."""
        rows = self._fetch_rows(device_id, metric_name, hours)
        if len(rows) < 10:
            return []

        values = [r["value"] for r in rows]
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

        if std == 0:
            return []

        anomalies = []
        for row in rows:
            z = abs(row["value"] - mean) / std
            if z >= z_threshold:
                anomalies.append(AnomalyPoint(
                    timestamp=row["timestamp"],
                    value=row["value"],
                    expected=mean,
                    deviation=z,
                ))
        return anomalies

    def compute_statistics(
        self,
        device_id: str,
        metric_name: str,
        hours: float = 24.0,
    ) -> Optional[dict]:
        """Compute basic statistics for a metric."""
        values = self._fetch_values(device_id, metric_name, hours)
        if not values:
            return None

        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        std = math.sqrt(variance)
        sorted_vals = sorted(values)
        median = sorted_vals[n // 2] if n % 2 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

        return {
            "count": n,
            "mean": mean,
            "std": std,
            "min": min(values),
            "max": max(values),
            "median": median,
        }

    def _fetch_values(self, device_id: str, metric_name: str, hours: float) -> list[float]:
        rows = self._fetch_rows(device_id, metric_name, hours)
        return [r["value"] for r in rows]

    def _fetch_rows(self, device_id: str, metric_name: str, hours: float) -> list[dict]:
        if not self._store or not hasattr(self._store, "query_timeseries"):
            return []
        end = time.time()
        start = end - hours * 3600
        return self._store.query_timeseries(
            metric_name=metric_name, device_id=device_id,
            start_time=start, end_time=end, limit=10000,
        )
