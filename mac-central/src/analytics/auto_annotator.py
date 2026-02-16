"""Auto annotation pipeline.

Converts high-confidence detection results into labeled datasets
in COCO or YOLO format for model retraining.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AnnotatedSample:
    """A single annotated detection sample."""
    image_id: int
    device_id: str
    timestamp: float
    width: int
    height: int
    annotations: list[dict] = field(default_factory=list)


class AutoAnnotator:
    """Generates training annotations from high-confidence detections."""

    def __init__(
        self,
        detection_store=None,
        min_confidence: float = 0.9,
        image_width: int = 1920,
        image_height: int = 1080,
    ) -> None:
        self._store = detection_store
        self._min_confidence = min_confidence
        self._width = image_width
        self._height = image_height
        self._class_map: dict[str, int] = {}
        self._next_class_id = 0

    def _get_class_id(self, class_name: str) -> int:
        if class_name not in self._class_map:
            self._class_map[class_name] = self._next_class_id
            self._next_class_id += 1
        return self._class_map[class_name]

    def collect_samples(
        self,
        device_id: str = "",
        hours: float = 24.0,
        limit: int = 500,
    ) -> list[AnnotatedSample]:
        """Collect high-confidence detections as annotation samples."""
        if not self._store:
            return []

        since = time.time() - hours * 3600
        events = self._store.query(since=since, limit=limit * 2, device_id=device_id)

        samples = []
        for idx, evt in enumerate(events):
            dets = evt.get("detections", [])
            high_conf = [d for d in dets if d.get("confidence", 0) >= self._min_confidence]
            if not high_conf:
                continue

            annotations = []
            for d in high_conf:
                class_name = d.get("class_name", "unknown")
                annotations.append({
                    "class_name": class_name,
                    "class_id": self._get_class_id(class_name),
                    "confidence": d.get("confidence", 0),
                    "x_min": d.get("x_min", 0),
                    "y_min": d.get("y_min", 0),
                    "x_max": d.get("x_max", 0),
                    "y_max": d.get("y_max", 0),
                })

            samples.append(AnnotatedSample(
                image_id=idx,
                device_id=evt.get("device_id", ""),
                timestamp=evt.get("timestamp", 0),
                width=self._width,
                height=self._height,
                annotations=annotations,
            ))

            if len(samples) >= limit:
                break

        return samples

    def export_coco(self, samples: list[AnnotatedSample]) -> dict:
        """Export samples in COCO JSON format."""
        images = []
        annotations = []
        ann_id = 1

        for s in samples:
            images.append({
                "id": s.image_id,
                "width": s.width,
                "height": s.height,
                "file_name": f"{s.device_id}_{s.image_id}.jpg",
            })
            for a in s.annotations:
                x_min = a["x_min"] * s.width
                y_min = a["y_min"] * s.height
                x_max = a["x_max"] * s.width
                y_max = a["y_max"] * s.height
                w = x_max - x_min
                h = y_max - y_min
                annotations.append({
                    "id": ann_id,
                    "image_id": s.image_id,
                    "category_id": a["class_id"],
                    "bbox": [x_min, y_min, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                })
                ann_id += 1

        categories = [
            {"id": cid, "name": name}
            for name, cid in self._class_map.items()
        ]

        return {
            "images": images,
            "annotations": annotations,
            "categories": categories,
        }

    def export_yolo(self, samples: list[AnnotatedSample]) -> list[str]:
        """Export samples in YOLO TXT format (one string per image).

        Format: class_id center_x center_y width height (all normalized).
        """
        lines = []
        for s in samples:
            image_lines = []
            for a in s.annotations:
                cx = (a["x_min"] + a["x_max"]) / 2
                cy = (a["y_min"] + a["y_max"]) / 2
                w = a["x_max"] - a["x_min"]
                h = a["y_max"] - a["y_min"]
                image_lines.append(f"{a['class_id']} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            lines.append("\n".join(image_lines))
        return lines
