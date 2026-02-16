"""Cross-camera re-identification engine.

Matches objects across cameras using feature vector similarity.
Uses cosine similarity on feature vectors stored in DetectionStore.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReIDMatch:
    """A re-identification match between two detections."""
    source_device_id: str
    target_device_id: str
    similarity: float
    source_timestamp: float
    target_timestamp: float
    class_name: str


@dataclass
class ReIDTrack:
    """A tracked identity across cameras."""
    track_id: str
    class_name: str
    sightings: list[dict] = field(default_factory=list)


class ReIDEngine:
    """Cross-camera re-identification using feature vector similarity."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        time_window_seconds: float = 300.0,
    ) -> None:
        self._threshold = similarity_threshold
        self._time_window = time_window_seconds
        self._feature_store: list[dict] = []
        self._tracks: dict[str, ReIDTrack] = {}
        self._next_track_id = 1

    def register_feature(
        self,
        device_id: str,
        class_name: str,
        feature_vector: list[float],
        timestamp: float = 0,
    ) -> Optional[str]:
        """Register a feature vector and attempt to match with existing tracks.

        Returns track_id if matched or newly created.
        """
        ts = timestamp or time.time()
        entry = {
            "device_id": device_id,
            "class_name": class_name,
            "feature_vector": feature_vector,
            "timestamp": ts,
        }

        # Try to match against recent features from other devices
        best_match = None
        best_sim = 0.0

        cutoff = ts - self._time_window
        for existing in self._feature_store:
            if existing["device_id"] == device_id:
                continue  # skip same device
            if existing["timestamp"] < cutoff:
                continue
            if existing["class_name"] != class_name:
                continue

            sim = self._cosine_similarity(feature_vector, existing["feature_vector"])
            if sim >= self._threshold and sim > best_sim:
                best_sim = sim
                best_match = existing

        if best_match and "track_id" in best_match:
            track_id = best_match["track_id"]
            entry["track_id"] = track_id
            self._tracks[track_id].sightings.append({
                "device_id": device_id,
                "timestamp": ts,
                "similarity": best_sim,
            })
            logger.info(
                f"ReID match: track={track_id} {best_match['device_id']}→{device_id} "
                f"sim={best_sim:.3f}"
            )
        else:
            track_id = f"track-{self._next_track_id:04d}"
            self._next_track_id += 1
            entry["track_id"] = track_id
            self._tracks[track_id] = ReIDTrack(
                track_id=track_id,
                class_name=class_name,
                sightings=[{"device_id": device_id, "timestamp": ts, "similarity": 1.0}],
            )

        self._feature_store.append(entry)
        self._prune_old(ts)
        return track_id

    def find_matches(
        self,
        feature_vector: list[float],
        class_name: str = "",
        exclude_device: str = "",
        top_k: int = 5,
    ) -> list[ReIDMatch]:
        """Find top-k matches for a feature vector."""
        now = time.time()
        cutoff = now - self._time_window
        matches = []

        for entry in self._feature_store:
            if entry["timestamp"] < cutoff:
                continue
            if exclude_device and entry["device_id"] == exclude_device:
                continue
            if class_name and entry["class_name"] != class_name:
                continue

            sim = self._cosine_similarity(feature_vector, entry["feature_vector"])
            if sim >= self._threshold:
                matches.append(ReIDMatch(
                    source_device_id=exclude_device,
                    target_device_id=entry["device_id"],
                    similarity=sim,
                    source_timestamp=now,
                    target_timestamp=entry["timestamp"],
                    class_name=entry["class_name"],
                ))

        matches.sort(key=lambda m: -m.similarity)
        return matches[:top_k]

    def get_track(self, track_id: str) -> Optional[ReIDTrack]:
        return self._tracks.get(track_id)

    def list_tracks(self, min_sightings: int = 2) -> list[ReIDTrack]:
        """List tracks with at least min_sightings across devices."""
        return [
            t for t in self._tracks.values()
            if len(t.sightings) >= min_sightings
        ]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _prune_old(self, now: float) -> None:
        cutoff = now - self._time_window * 2
        self._feature_store = [e for e in self._feature_store if e["timestamp"] >= cutoff]
