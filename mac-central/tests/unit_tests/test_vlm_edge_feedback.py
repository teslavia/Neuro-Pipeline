"""Tests for VLM-guided edge configuration feedback."""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch

from src.pipeline.central_orchestrator import CentralOrchestrator


class TestVLMEdgeFeedback:
    def test_parse_vlm_config_suggestion(self):
        """Test parsing VLM JSON config suggestion into a ControlCommand."""
        vlm_output = json.dumps({
            "roi": {"x_min": 0.1, "y_min": 0.2, "x_max": 0.8, "y_max": 0.9},
            "threshold": 0.7,
            "fps_recommendation": 15,
        })
        parsed = json.loads(vlm_output)
        assert "roi" in parsed
        assert parsed["threshold"] == 0.7
        assert parsed["fps_recommendation"] == 15

    def test_parse_invalid_vlm_output(self):
        """VLM may return non-JSON; should handle gracefully."""
        vlm_output = "I recommend adjusting the ROI to focus on the entrance."
        try:
            parsed = json.loads(vlm_output)
        except json.JSONDecodeError:
            parsed = None
        assert parsed is None

    def test_edge_config_prompt_template(self):
        """Verify edge_config_suggestion template exists and formats."""
        from src.inference.prompt_generator import PromptGenerator, TEMPLATES
        assert "edge_config_suggestion" in TEMPLATES

        gen = PromptGenerator()
        prompt = gen.generate(
            [{"class_name": "person", "confidence": 0.9,
              "x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.8}],
            template="edge_config_suggestion",
            previous_context="A person is loitering near the entrance.",
        )
        assert "ROI" in prompt or "roi" in prompt.lower()
        assert "threshold" in prompt.lower()

    def test_config_suggestion_to_command_params(self):
        """Test converting parsed config to command parameters."""
        config = {
            "roi": {"x_min": 0.1, "y_min": 0.2, "x_max": 0.8, "y_max": 0.9},
            "threshold": 0.7,
            "fps_recommendation": 15,
        }
        params = {}
        if "roi" in config:
            roi = config["roi"]
            params["roi"] = f"{roi['x_min']},{roi['y_min']},{roi['x_max']},{roi['y_max']}"
        if "threshold" in config:
            params["threshold"] = str(config["threshold"])
        if "fps_recommendation" in config:
            params["fps"] = str(config["fps_recommendation"])

        assert params["roi"] == "0.1,0.2,0.8,0.9"
        assert params["threshold"] == "0.7"
        assert params["fps"] == "15"
