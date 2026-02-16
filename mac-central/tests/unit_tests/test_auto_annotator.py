"""Tests for auto annotation pipeline."""

import time
import json
import pytest
from pathlib import Path

from src.analytics.auto_annotator import AutoAnnotator, AnnotatedSample
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestAutoAnnotator:
    def test_no_store(self):
        ann = AutoAnnotator(detection_store=None)
        samples = ann.collect_samples()
        assert samples == []

    def test_collect_high_confidence(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 100,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [
                {"class_name": "person", "confidence": 0.95,
                 "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8},
                {"class_name": "car", "confidence": 0.5,  # below threshold
                 "x_min": 0.6, "y_min": 0.3, "x_max": 0.9, "y_max": 0.7},
            ],
        })

        ann = AutoAnnotator(detection_store=store, min_confidence=0.9)
        samples = ann.collect_samples(hours=1.0)
        assert len(samples) == 1
        assert len(samples[0].annotations) == 1
        assert samples[0].annotations[0]["class_name"] == "person"

    def test_export_coco(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 50,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [
                {"class_name": "person", "confidence": 0.95,
                 "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8},
            ],
        })

        ann = AutoAnnotator(detection_store=store, min_confidence=0.9)
        samples = ann.collect_samples(hours=1.0)
        coco = ann.export_coco(samples)

        assert "images" in coco
        assert "annotations" in coco
        assert "categories" in coco
        assert len(coco["images"]) == 1
        assert len(coco["annotations"]) == 1
        assert coco["annotations"][0]["bbox"][2] > 0  # width > 0

    def test_export_yolo(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 50,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [
                {"class_name": "person", "confidence": 0.95,
                 "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8},
            ],
        })

        ann = AutoAnnotator(detection_store=store, min_confidence=0.9)
        samples = ann.collect_samples(hours=1.0)
        yolo_lines = ann.export_yolo(samples)

        assert len(yolo_lines) == 1
        parts = yolo_lines[0].split()
        assert len(parts) == 5  # class_id cx cy w h
        assert float(parts[1]) == pytest.approx(0.3, abs=0.01)  # center_x

    def test_limit(self, store):
        now = time.time()
        for i in range(20):
            store.record({
                "type": "detection", "timestamp": now - 1000 + i * 10,
                "frame_id": i, "device_id": "edge-001",
                "detections": [
                    {"class_name": "person", "confidence": 0.95,
                     "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8},
                ],
            })

        ann = AutoAnnotator(detection_store=store, min_confidence=0.9)
        samples = ann.collect_samples(hours=1.0, limit=5)
        assert len(samples) <= 5

    def test_class_map(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 50,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [
                {"class_name": "person", "confidence": 0.95,
                 "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8},
                {"class_name": "car", "confidence": 0.92,
                 "x_min": 0.6, "y_min": 0.3, "x_max": 0.9, "y_max": 0.7},
            ],
        })

        ann = AutoAnnotator(detection_store=store, min_confidence=0.9)
        samples = ann.collect_samples(hours=1.0)
        coco = ann.export_coco(samples)
        assert len(coco["categories"]) == 2
