"""Unit tests for prompt generator."""

import pytest

from src.llm_vlm.prompt_generator import PromptGenerator


class TestPromptGenerator:
    """Tests for PromptGenerator."""

    def test_generate_scene_analysis(self, sample_detections):
        gen = PromptGenerator(default_template="scene_analysis")
        prompt = gen.generate(sample_detections)

        assert "person" in prompt
        assert "car" in prompt
        assert "safety" in prompt.lower()

    def test_generate_person_behavior(self, sample_detections):
        gen = PromptGenerator()
        prompt = gen.generate(sample_detections, template="person_behavior")

        assert "0.20" in prompt  # x_min
        assert "95.0%" in prompt  # confidence

    def test_generate_empty_detections(self):
        gen = PromptGenerator()
        prompt = gen.generate([])

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_available_templates(self):
        templates = PromptGenerator.available_templates()

        assert "scene_analysis" in templates
        assert "person_behavior" in templates
        assert "anomaly_detection" in templates
        assert "multi_object" in templates

    def test_generate_multi_object(self, sample_detections):
        gen = PromptGenerator()
        prompt = gen.generate(sample_detections, template="multi_object")

        assert "person" in prompt
        assert "car" in prompt
        assert "spatial" in prompt.lower()
