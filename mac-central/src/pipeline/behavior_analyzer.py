"""Central-side behavior analysis using detection history patterns."""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BehaviorType(Enum):
    LOITERING = "loitering"
    RUNNING = "running"
    LINGERING = "lingering"
    CROWD = "crowd"
    UNUSUAL_TIME = "unusual_time"


@dataclass
class BehaviorEvent:
    behavior_type: BehaviorType
    device_id: str
    confidence: float
    description: str
    timestamp: float
    metadata: Dict[str, Any]


class BehaviorAnalyzer:
    """Analyzes detection history to identify behavioral patterns.

    Works with the detection store to query historical data and
    identify patterns like loitering, crowding, and unusual activity.
    """

    def __init__(self, detection_store=None,
                 loiter_threshold_seconds: float = 120.0,
                 crowd_threshold: int = 5,
                 analysis_window_seconds: float = 300.0) -> None:
        self._store = detection_store
        self._loiter_threshold = loiter_threshold_seconds
        self._crowd_threshold = crowd_threshold
        self._analysis_window = analysis_window_seconds
        logger.info("BehaviorAnalyzer initialized (loiter=%.0fs, crowd=%d, window=%.0fs)",
                    loiter_threshold_seconds, crowd_threshold, analysis_window_seconds)

    def analyze(self, device_id: str, current_detections: List[Dict[str, Any]],
                timestamp: float = 0) -> List[BehaviorEvent]:
        """Analyze current + historical detections for behavioral patterns."""
        ts = timestamp or time.time()
        events: List[BehaviorEvent] = []

        # Check crowd
        crowd = self._check_crowd(device_id, current_detections, ts)
        if crowd:
            events.append(crowd)

        # Check loitering (needs history)
        if self._store:
            loiter = self._check_loitering(device_id, current_detections, ts)
            if loiter:
                events.append(loiter)

        return events

    def _check_crowd(self, device_id: str, detections: List[Dict],
                     timestamp: float) -> Optional[BehaviorEvent]:
        """Detect crowding: many objects of same class in one frame."""
        class_counts: Dict[str, int] = {}
        for d in detections:
            cn = d.get("class_name", "")
            class_counts[cn] = class_counts.get(cn, 0) + 1

        for class_name, count in class_counts.items():
            if count >= self._crowd_threshold:
                return BehaviorEvent(
                    behavior_type=BehaviorType.CROWD,
                    device_id=device_id,
                    confidence=min(1.0, count / (self._crowd_threshold * 2)),
                    description=f"{count} {class_name} objects detected (threshold: {self._crowd_threshold})",
                    timestamp=timestamp,
                    metadata={"class_name": class_name, "count": count},
                )
        return None

    def _check_loitering(self, device_id: str, current_detections: List[Dict],
                         timestamp: float) -> Optional[BehaviorEvent]:
        """Detect loitering: same class detected repeatedly over time window."""
        if not self._store or not hasattr(self._store, 'query_timeseries'):
            return None

        since = timestamp - self._analysis_window
        try:
            history = self._store.query(since=since, until=timestamp,
                                        device_id=device_id, limit=200)
        except Exception as e:
            logger.warning("Failed to query history for loitering check: %s", e)
            return None

        if not history:
            return None

        # Count how many distinct time buckets (10s each) have person detections
        person_buckets = set()
        for event in history:
            dets = event.get("detections", [])
            for d in dets:
                if d.get("class_name") == "person":
                    bucket = int(event.get("timestamp", 0) / 10)
                    person_buckets.add(bucket)

        # Also check current frame
        has_person_now = any(d.get("class_name") == "person" for d in current_detections)
        if not has_person_now:
            return None

        duration_estimate = len(person_buckets) * 10.0
        if duration_estimate >= self._loiter_threshold:
            return BehaviorEvent(
                behavior_type=BehaviorType.LOITERING,
                device_id=device_id,
                confidence=min(1.0, duration_estimate / (self._loiter_threshold * 2)),
                description=f"Person detected across ~{duration_estimate:.0f}s window (threshold: {self._loiter_threshold:.0f}s)",
                timestamp=timestamp,
                metadata={"duration_estimate": duration_estimate,
                          "bucket_count": len(person_buckets)},
            )
        return None
