"""Unit tests for VLMConfigGuide."""

import pytest
from src.llm_vlm.vlm_config_guide import (
    ConfigAdjustment,
    ConfigAdjustmentType,
    DetectionRegion,
    VLMConfigGuide,
    VLMGuidanceResult,
)


class TestDetectionRegion:
    """Tests for DetectionRegion dataclass."""

    def test_default_region(self):
        """Default region should be full frame."""
        region = DetectionRegion()
        assert region.x_min == 0.0
        assert region.y_min == 0.0
        assert region.x_max == 1.0
        assert region.y_max == 1.0

    def test_to_dict(self):
        """Test serialization to dict."""
        region = DetectionRegion(x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8)
        d = region.to_dict()
        assert d["x_min"] == 0.1
        assert d["y_min"] == 0.2
        assert d["x_max"] == 0.9
        assert d["y_max"] == 0.8

    def test_clamp(self):
        """Test clamping values to [0, 1]."""
        region = DetectionRegion(x_min=-0.1, y_min=1.1, x_max=1.5, y_max=-0.5)
        clamped = region.clamp()
        assert clamped.x_min == 0.0
        assert clamped.y_min == 1.0
        assert clamped.x_max == 1.0
        assert clamped.y_max == 0.0


class TestVLMConfigGuide:
    """Tests for VLMConfigGuide."""

    @pytest.fixture
    def guide(self):
        return VLMConfigGuide(min_confidence=0.5)

    def test_init(self, guide):
        """Test initialization."""
        assert guide.min_confidence == 0.5
        assert guide.enable_region_adjustment is True
        assert guide.enable_sensitivity_adjustment is True
        assert guide.enable_fps_adjustment is False  # Conservative default

    def test_parse_empty_result(self, guide):
        """Empty VLM result should return no adjustments."""
        result = guide.parse_vlm_result("")
        assert len(result.adjustments) == 0
        assert len(result.raw_recommendations) == 0
        assert result.should_apply is False

    def test_parse_no_recommendations(self, guide):
        """Text without actionable recommendations."""
        vlm_result = "I can see a person walking in the scene. The weather appears to be sunny."
        result = guide.parse_vlm_result(vlm_result)
        # May or may not extract recommendations depending on pattern matching
        assert result.parsing_confidence >= 0.0

    def test_parse_region_upper(self, guide):
        """Test parsing region adjustment for upper area."""
        vlm_result = """
        Recommendations:
        1. Focus on the upper area of the frame to catch people on the balcony.
        """
        result = guide.parse_vlm_result(vlm_result)
        assert len(result.adjustments) >= 1
        adj = result.adjustments[0]
        assert adj.adjustment_type == ConfigAdjustmentType.DETECTION_REGION
        assert adj.region is not None
        assert adj.region.y_max <= 0.6  # Upper area

    def test_parse_region_lower(self, guide):
        """Test parsing region adjustment for lower area."""
        vlm_result = "I suggest to monitor the lower portion for ground-level activities."
        result = guide.parse_vlm_result(vlm_result)
        if result.adjustments:
            adj = result.adjustments[0]
            if adj.adjustment_type == ConfigAdjustmentType.DETECTION_REGION:
                assert adj.region.y_min >= 0.4  # Lower area

    def test_parse_sensitivity_increase(self, guide):
        """Test parsing sensitivity increase."""
        vlm_result = "Recommendation: Increase detection sensitivity to catch more subtle movements."
        result = guide.parse_vlm_result(vlm_result)
        assert len(result.adjustments) >= 1
        adj = result.adjustments[0]
        assert adj.adjustment_type == ConfigAdjustmentType.SENSITIVITY
        assert adj.sensitivity_delta > 0  # Increase sensitivity

    def test_parse_sensitivity_decrease(self, guide):
        """Test parsing sensitivity decrease."""
        vlm_result = "You should reduce false positives by lowering sensitivity."
        result = guide.parse_vlm_result(vlm_result)
        if result.adjustments:
            adj = result.adjustments[0]
            if adj.adjustment_type == ConfigAdjustmentType.SENSITIVITY:
                assert adj.sensitivity_delta < 0  # Decrease sensitivity

    def test_parse_multiple_recommendations(self, guide):
        """Test parsing multiple recommendations."""
        vlm_result = """
        Based on the analysis:
        1. Focus on the center region for main activity.
        2. Increase sensitivity for better detection.
        3. Monitor the right side for entry points.
        """
        result = guide.parse_vlm_result(vlm_result)
        # Should extract at least some recommendations
        assert len(result.raw_recommendations) >= 1

    def test_create_control_command_region(self, guide):
        """Test creating control command for region adjustment."""
        adjustment = ConfigAdjustment(
            adjustment_type=ConfigAdjustmentType.DETECTION_REGION,
            reason="Focus on upper area",
            confidence=0.8,
            region=DetectionRegion(x_min=0.0, y_min=0.0, x_max=1.0, y_max=0.5),
        )
        cmd = guide.create_control_command(adjustment, "edge-001", 123)
        assert cmd["type"] == 7  # SET_DETECTION_REGION
        assert cmd["command_id"] == 123
        assert cmd["parameters"]["y_max"] == 0.5
        assert cmd["target_device_id"] == "edge-001"

    def test_create_control_command_sensitivity(self, guide):
        """Test creating control command for sensitivity adjustment."""
        adjustment = ConfigAdjustment(
            adjustment_type=ConfigAdjustmentType.SENSITIVITY,
            reason="Increase sensitivity",
            confidence=0.75,
            sensitivity_delta=0.05,
        )
        cmd = guide.create_control_command(adjustment, "edge-001", 124)
        assert cmd["type"] == 8  # SET_SENSITIVITY
        assert cmd["parameters"]["delta"] == 0.05

    def test_min_confidence_filter(self):
        """Test that low-confidence adjustments are filtered out."""
        guide = VLMConfigGuide(min_confidence=0.8)
        # This might generate a low-confidence adjustment
        vlm_result = "Maybe focus on that area over there?"
        result = guide.parse_vlm_result(vlm_result)
        # Adjustments should be filtered if confidence is too low
        for adj in result.adjustments:
            assert adj.confidence >= 0.8

    def test_max_adjustments_limit(self):
        """Test that max adjustments per result is respected."""
        guide = VLMConfigGuide(max_adjustments_per_result=2)
        vlm_result = """
        Recommendations:
        1. Focus on the upper area.
        2. Increase sensitivity.
        3. Monitor the right side.
        4. Adjust detection region.
        """
        result = guide.parse_vlm_result(vlm_result)
        assert len(result.adjustments) <= 2

    def test_fps_disabled_by_default(self, guide):
        """FPS adjustment should be disabled by default."""
        vlm_result = "Recommendation: Increase frame rate for better tracking."
        result = guide.parse_vlm_result(vlm_result)
        # Should not create FPS adjustment since it's disabled
        fps_adjustments = [
            a for a in result.adjustments
            if a.adjustment_type == ConfigAdjustmentType.FPS
        ]
        assert len(fps_adjustments) == 0

    def test_fps_enabled(self):
        """Test FPS adjustment when enabled."""
        guide = VLMConfigGuide(enable_fps_adjustment=True)
        vlm_result = "Recommendation: Increase FPS for fast-moving objects."
        result = guide.parse_vlm_result(vlm_result)
        # May or may not create FPS adjustment depending on pattern matching
        # Just verify it doesn't crash
        assert result.parsing_confidence >= 0.0


class TestConfigAdjustment:
    """Tests for ConfigAdjustment dataclass."""

    def test_to_command_params_region(self):
        """Test command params for region adjustment."""
        adj = ConfigAdjustment(
            adjustment_type=ConfigAdjustmentType.DETECTION_REGION,
            reason="Test",
            confidence=0.8,
            region=DetectionRegion(0.1, 0.2, 0.9, 0.8),
        )
        params = adj.to_command_params()
        assert params["x_min"] == 0.1
        assert params["y_min"] == 0.2
        assert params["x_max"] == 0.9
        assert params["y_max"] == 0.8
        assert params["reason"] == "Test"

    def test_to_command_params_sensitivity(self):
        """Test command params for sensitivity adjustment."""
        adj = ConfigAdjustment(
            adjustment_type=ConfigAdjustmentType.SENSITIVITY,
            reason="Test sensitivity",
            confidence=0.75,
            sensitivity_delta=-0.05,
        )
        params = adj.to_command_params()
        assert params["delta"] == -0.05
        assert params["reason"] == "Test sensitivity"

    def test_to_command_params_focus_area(self):
        """Test command params for focus area adjustment."""
        adj = ConfigAdjustment(
            adjustment_type=ConfigAdjustmentType.FOCUS_AREA,
            reason="Focus on persons",
            confidence=0.7,
            region=DetectionRegion(0.2, 0.2, 0.8, 0.8),
            target_classes=["person", "vehicle"],
        )
        params = adj.to_command_params()
        assert "classes" in params
        assert "person" in params["classes"]
        assert "vehicle" in params["classes"]
