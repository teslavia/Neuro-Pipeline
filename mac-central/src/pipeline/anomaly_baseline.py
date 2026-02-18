"""Anomaly baseline learning and detection.

Builds statistical baselines from historical detection patterns
and scores new observations against them using z-score analysis.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BaselineStats:
    """Statistical baseline for a metric."""
    metric_name: str
    device_id: str
    mean: float = 0.0
    std_dev: float = 0.0
    sample_count: int = 0
    last_updated: float = 0.0


@dataclass
class AnomalyScore:
    """Anomaly detection result."""
    metric_name: str
    device_id: str
    value: float
    z_score: float
    is_anomaly: bool
    baseline_mean: float
    baseline_std: float


class AnomalyBaseline:
    """Learns normal baselines and detects anomalies via z-score."""

    def __init__(
        self,
        detection_store=None,
        baseline_window_hours: float = 168.0,
        z_score_threshold: float = 3.0,
        min_samples: int = 50,
    ) -> None:
        self._store = detection_store
        self._window_hours = baseline_window_hours
        self._z_threshold = z_score_threshold
        self._min_samples = min_samples
        self._baselines: dict[str, BaselineStats] = {}

    def learn_baseline(self, device_id: str, metric_name: str) -> Optional[BaselineStats]:
        """Build baseline statistics from historical timeseries data."""
        if not self._store or not hasattr(self._store, "query_timeseries"):
            return None

        end_time = time.time()
        start_time = end_time - self._window_hours * 3600

        rows = self._store.query_timeseries(
            metric_name=metric_name,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            aggregation="avg",
            bucket_seconds=0,
            limit=10000,
        )

        values = [r["value"] for r in rows]
        if len(values) < self._min_samples:
            logger.debug(
                f"Insufficient samples for baseline: {len(values)} < {self._min_samples}"
            )
            return None

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)

        key = f"{device_id}:{metric_name}"
        baseline = BaselineStats(
            metric_name=metric_name,
            device_id=device_id,
            mean=mean,
            std_dev=std_dev,
            sample_count=len(values),
            last_updated=time.time(),
        )
        self._baselines[key] = baseline
        logger.info(
            f"Baseline learned: {key} mean={mean:.2f} std={std_dev:.2f} n={len(values)}"
        )
        return baseline

    def score(self, device_id: str, metric_name: str, value: float) -> AnomalyScore:
        """Score a value against the learned baseline."""
        key = f"{device_id}:{metric_name}"
        baseline = self._baselines.get(key)

        if not baseline or baseline.sample_count < self._min_samples:
            return AnomalyScore(
                metric_name=metric_name,
                device_id=device_id,
                value=value,
                z_score=0.0,
                is_anomaly=False,
                baseline_mean=0.0,
                baseline_std=0.0,
            )

        if baseline.std_dev == 0:
            z = 0.0 if value == baseline.mean else float("inf")
        else:
            z = abs(value - baseline.mean) / baseline.std_dev

        is_anomaly = z >= self._z_threshold

        if is_anomaly:
            logger.warning(
                f"Anomaly detected: {key} value={value:.2f} z={z:.2f} "
                f"(mean={baseline.mean:.2f} std={baseline.std_dev:.2f})"
            )

        return AnomalyScore(
            metric_name=metric_name,
            device_id=device_id,
            value=value,
            z_score=z,
            is_anomaly=is_anomaly,
            baseline_mean=baseline.mean,
            baseline_std=baseline.std_dev,
        )

    def get_baseline(self, device_id: str, metric_name: str) -> Optional[BaselineStats]:
        """Get the current baseline for a device/metric pair."""
        return self._baselines.get(f"{device_id}:{metric_name}")

    def list_baselines(self) -> list[BaselineStats]:
        """List all learned baselines."""
        return list(self._baselines.values())
