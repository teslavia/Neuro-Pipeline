"""Tests for auto event report generator."""

import time
import json
import pytest
from pathlib import Path

from src.reporting.report_generator import ReportGenerator, EventReport
from src.storage.detection_store import DetectionStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = DetectionStore(db, retention_days=7)
    yield s
    s.close()


class TestReportGenerator:
    def test_no_store(self):
        gen = ReportGenerator(detection_store=None)
        report = gen.generate()
        assert "No detection store" in report.summary

    def test_empty_store(self, store):
        gen = ReportGenerator(detection_store=store)
        report = gen.generate(time_range_hours=1.0)
        assert report.total_events == 0
        assert "No events" in report.summary

    def test_detection_summary(self, store):
        now = time.time()
        for i in range(10):
            store.record({
                "type": "detection", "timestamp": now - 100 + i,
                "frame_id": i, "device_id": "edge-001",
                "detections": [
                    {"class_name": "person", "confidence": 0.9},
                    {"class_name": "car", "confidence": 0.8},
                ],
            })

        gen = ReportGenerator(detection_store=store)
        report = gen.generate(device_id="edge-001", time_range_hours=1.0)
        assert report.total_events == 10
        assert len(report.sections) >= 1
        assert "Detection Summary" in report.sections[0].title
        assert "person" in report.sections[0].content

    def test_report_to_json(self, store):
        gen = ReportGenerator(detection_store=store)
        report = gen.generate()
        j = report.to_json()
        parsed = json.loads(j)
        assert "report_id" in parsed
        assert "sections" in parsed

    def test_report_to_dict(self, store):
        gen = ReportGenerator(detection_store=store)
        report = gen.generate()
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "device_id" in d

    def test_device_filter(self, store):
        now = time.time()
        store.record({
            "type": "detection", "timestamp": now - 10,
            "frame_id": 1, "device_id": "edge-001",
            "detections": [{"class_name": "person", "confidence": 0.9}],
        })
        store.record({
            "type": "detection", "timestamp": now - 5,
            "frame_id": 2, "device_id": "edge-002",
            "detections": [{"class_name": "car", "confidence": 0.8}],
        })

        gen = ReportGenerator(detection_store=store)
        report = gen.generate(device_id="edge-001")
        assert report.total_events == 1
