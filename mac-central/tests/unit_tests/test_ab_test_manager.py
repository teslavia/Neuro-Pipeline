"""Tests for A/B model testing manager."""

import pytest
from src.model_management.ab_test_manager import (
    ABTestManager, ABGroup, ABTestResult, VariantMetrics,
)


class TestABTestManager:
    def test_assign_group_deterministic(self):
        mgr = ABTestManager(traffic_split=0.5)
        group = mgr.assign_group("edge-001")
        assert group in (ABGroup.CONTROL, ABGroup.TREATMENT)
        # Same device always gets same group
        assert mgr.assign_group("edge-001") == group

    def test_get_variant(self):
        mgr = ABTestManager(control_variant="modelA", treatment_variant="modelB")
        variant = mgr.get_variant("edge-001")
        assert variant in ("modelA", "modelB")

    def test_get_group_unassigned(self):
        mgr = ABTestManager()
        assert mgr.get_group("unknown") is None

    def test_record_inference(self):
        mgr = ABTestManager(control_variant="v1", treatment_variant="v2")
        mgr.record_inference("v1", 50.0)
        mgr.record_inference("v1", 30.0)
        metrics = mgr.get_metrics()
        assert metrics["v1"].total_inferences == 2
        assert metrics["v1"].avg_latency_ms == 40.0

    def test_record_detection(self):
        mgr = ABTestManager(control_variant="v1", treatment_variant="v2")
        mgr.record_detection("v1", correct=True)
        mgr.record_detection("v1", correct=True)
        mgr.record_detection("v1", correct=False)
        metrics = mgr.get_metrics()
        assert metrics["v1"].total_detections == 3
        assert metrics["v1"].correct_detections == 2
        assert abs(metrics["v1"].accuracy - 2 / 3) < 0.01

    def test_evaluate_insufficient_samples(self):
        mgr = ABTestManager(min_samples=100)
        mgr.record_inference("v1", 50.0)
        result = mgr.evaluate()
        assert result.sufficient_samples is False
        assert result.confidence == 0.0

    def test_evaluate_accuracy_winner(self):
        mgr = ABTestManager(
            control_variant="v1", treatment_variant="v2",
            min_samples=2, metric="accuracy",
        )
        # v1: 100% accuracy
        for _ in range(5):
            mgr.record_inference("v1", 50.0)
            mgr.record_detection("v1", correct=True)
        # v2: 40% accuracy
        for i in range(5):
            mgr.record_inference("v2", 40.0)
            mgr.record_detection("v2", correct=(i < 2))

        result = mgr.evaluate()
        assert result.sufficient_samples is True
        assert result.winner == "v1"

    def test_evaluate_latency_winner(self):
        mgr = ABTestManager(
            control_variant="v1", treatment_variant="v2",
            min_samples=2, metric="latency",
        )
        for _ in range(5):
            mgr.record_inference("v1", 100.0)
            mgr.record_inference("v2", 50.0)

        result = mgr.evaluate()
        assert result.winner == "v2"  # lower latency wins

    def test_reset(self):
        mgr = ABTestManager()
        mgr.assign_group("edge-001")
        mgr.record_inference("v1", 50.0)
        mgr.reset()
        assert mgr.get_group("edge-001") is None
        metrics = mgr.get_metrics()
        assert metrics["v1"].total_inferences == 0

    def test_traffic_split_bounds(self):
        mgr = ABTestManager(traffic_split=1.5)
        assert mgr._traffic_split == 1.0
        mgr2 = ABTestManager(traffic_split=-0.5)
        assert mgr2._traffic_split == 0.0
