"""A/B model testing manager.

Assigns devices to test groups, collects per-variant metrics,
and determines the winning model variant.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ABGroup(str, Enum):
    CONTROL = "control"
    TREATMENT = "treatment"


@dataclass
class VariantMetrics:
    """Accumulated metrics for one model variant."""
    variant_name: str
    total_inferences: int = 0
    total_latency_ms: float = 0.0
    correct_detections: int = 0
    total_detections: int = 0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_inferences, 1)

    @property
    def accuracy(self) -> float:
        return self.correct_detections / max(self.total_detections, 1)


@dataclass
class ABTestResult:
    """Result of an A/B test evaluation."""
    winner: str
    control_metrics: VariantMetrics
    treatment_metrics: VariantMetrics
    confidence: float
    sufficient_samples: bool


class ABTestManager:
    """Manages A/B testing between two model variants."""

    def __init__(
        self,
        control_variant: str = "v1",
        treatment_variant: str = "v2",
        traffic_split: float = 0.5,
        min_samples: int = 100,
        metric: str = "accuracy",
    ) -> None:
        self._control = control_variant
        self._treatment = treatment_variant
        self._traffic_split = max(0.0, min(1.0, traffic_split))
        self._min_samples = min_samples
        self._metric = metric
        self._lock = threading.Lock()
        self._device_groups: dict[str, ABGroup] = {}
        self._metrics: dict[str, VariantMetrics] = {
            control_variant: VariantMetrics(variant_name=control_variant),
            treatment_variant: VariantMetrics(variant_name=treatment_variant),
        }

    def assign_group(self, device_id: str) -> ABGroup:
        """Assign a device to control or treatment group."""
        with self._lock:
            if device_id in self._device_groups:
                return self._device_groups[device_id]
            group = (
                ABGroup.TREATMENT
                if random.random() < self._traffic_split
                else ABGroup.CONTROL
            )
            self._device_groups[device_id] = group
            logger.info(f"A/B: device {device_id} → {group.value}")
            return group

    def get_group(self, device_id: str) -> Optional[ABGroup]:
        """Get the assigned group for a device, or None."""
        with self._lock:
            return self._device_groups.get(device_id)

    def get_variant(self, device_id: str) -> str:
        """Get the model variant name for a device."""
        group = self.assign_group(device_id)
        return self._control if group == ABGroup.CONTROL else self._treatment

    def record_inference(self, variant: str, latency_ms: float) -> None:
        """Record an inference event for a variant."""
        with self._lock:
            m = self._metrics.get(variant)
            if m:
                m.total_inferences += 1
                m.total_latency_ms += latency_ms

    def record_detection(self, variant: str, correct: bool) -> None:
        """Record a detection result for accuracy tracking."""
        with self._lock:
            m = self._metrics.get(variant)
            if m:
                m.total_detections += 1
                if correct:
                    m.correct_detections += 1

    def evaluate(self) -> ABTestResult:
        """Evaluate the A/B test and determine a winner."""
        with self._lock:
            ctrl = self._metrics[self._control]
            treat = self._metrics[self._treatment]

        sufficient = (
            ctrl.total_inferences >= self._min_samples
            and treat.total_inferences >= self._min_samples
        )

        if self._metric == "latency":
            ctrl_score = ctrl.avg_latency_ms
            treat_score = treat.avg_latency_ms
            # Lower latency is better
            winner = self._control if ctrl_score <= treat_score else self._treatment
            diff = abs(ctrl_score - treat_score) / max(ctrl_score, treat_score, 1)
        else:
            # Default: accuracy
            ctrl_score = ctrl.accuracy
            treat_score = treat.accuracy
            winner = self._control if ctrl_score >= treat_score else self._treatment
            diff = abs(ctrl_score - treat_score)

        confidence = min(diff * 10, 1.0) if sufficient else 0.0

        return ABTestResult(
            winner=winner,
            control_metrics=ctrl,
            treatment_metrics=treat,
            confidence=confidence,
            sufficient_samples=sufficient,
        )

    def get_metrics(self) -> dict[str, VariantMetrics]:
        """Return current metrics for both variants."""
        with self._lock:
            return dict(self._metrics)

    def reset(self) -> None:
        """Reset all metrics and group assignments."""
        with self._lock:
            self._device_groups.clear()
            for m in self._metrics.values():
                m.total_inferences = 0
                m.total_latency_ms = 0.0
                m.correct_detections = 0
                m.total_detections = 0
