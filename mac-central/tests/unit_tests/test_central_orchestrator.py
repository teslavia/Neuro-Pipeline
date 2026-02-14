"""Unit tests for CentralOrchestrator."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.application_logic.central_orchestrator import (
    CentralOrchestrator,
    VLMTriggerRule,
)
from src.config import AppConfig, VLMRuleConfig


@pytest.fixture
def orchestrator():
    return CentralOrchestrator(Path("models/test"))


@pytest.fixture
def orchestrator_custom_rules():
    rules = [
        VLMTriggerRule(class_name="car", min_confidence=0.9, prompt_template="vehicle"),
        VLMTriggerRule(class_name="person", min_confidence=0.7, prompt_template="person_behavior"),
    ]
    return CentralOrchestrator(Path("models/test"), vlm_rules=rules)


@pytest.mark.asyncio
async def test_default_vlm_rule(orchestrator):
    """Default rule triggers on person > 0.8."""
    result = MagicMock()
    result.frame_id = 1
    result.trace_id = "edge-1"
    result.frame_data = b""
    box = MagicMock()
    box.class_name = "person"
    box.confidence = 0.85
    box.x_min = box.y_min = 0.1
    box.x_max = box.y_max = 0.9
    result.boxes = [box]

    # No frame_data → no VLM triggered even if rule matches
    out = await orchestrator.process_detection(result)
    assert out is None


@pytest.mark.asyncio
async def test_custom_vlm_rule_match(orchestrator_custom_rules):
    """Custom rule triggers on car > 0.9."""
    rule = orchestrator_custom_rules._match_vlm_rule(
        [{"class_name": "car", "confidence": 0.95}]
    )
    assert rule is not None
    assert rule.prompt_template == "vehicle"


@pytest.mark.asyncio
async def test_custom_vlm_rule_no_match(orchestrator_custom_rules):
    """No rule matches when confidence is too low."""
    rule = orchestrator_custom_rules._match_vlm_rule(
        [{"class_name": "car", "confidence": 0.5}]
    )
    assert rule is None


@pytest.mark.asyncio
async def test_command_queue(orchestrator):
    """Commands are queued and retrievable."""
    cmd = MagicMock()
    cmd.type = 0
    cmd.command_id = 42

    await orchestrator.send_command(cmd)
    got = await asyncio.wait_for(orchestrator.get_pending_command(), timeout=1.0)
    assert got.command_id == 42


@pytest.mark.asyncio
async def test_handle_edge_event(orchestrator):
    """Edge events are processed without error."""
    event = MagicMock()
    event.type = 3
    event.description = "health"
    await orchestrator.handle_edge_event(event)


class TestVLMConfigIntegration:
    """Tests for VLM rules loaded from config.yaml."""

    def test_config_loads_vlm_rules(self, tmp_path):
        """VLM rules are parsed from YAML config."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "vlm_rules:\n"
            "  - class_name: fire\n"
            "    min_confidence: 0.6\n"
            "    prompt_template: anomaly_detection\n"
            "  - class_name: person\n"
            "    min_confidence: 0.75\n"
            "    prompt_template: person_behavior\n"
        )
        cfg = AppConfig.from_yaml(cfg_file)
        assert len(cfg.vlm_rules) == 2
        assert cfg.vlm_rules[0].class_name == "fire"
        assert cfg.vlm_rules[0].min_confidence == 0.6
        assert cfg.vlm_rules[1].prompt_template == "person_behavior"

    def test_config_default_vlm_rules(self):
        """Default config has one person rule."""
        cfg = AppConfig()
        assert len(cfg.vlm_rules) == 1
        assert cfg.vlm_rules[0].class_name == "person"

    def test_config_rules_to_orchestrator(self, tmp_path):
        """Config VLM rules wire through to orchestrator."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "vlm_rules:\n"
            "  - class_name: car\n"
            "    min_confidence: 0.9\n"
            "    prompt_template: scene_analysis\n"
        )
        cfg = AppConfig.from_yaml(cfg_file)
        rules = [
            VLMTriggerRule(
                class_name=r.class_name,
                min_confidence=r.min_confidence,
                prompt_template=r.prompt_template,
            )
            for r in cfg.vlm_rules
        ]
        orch = CentralOrchestrator(Path("models/test"), vlm_rules=rules)
        assert len(orch.vlm_rules) == 1
        assert orch.vlm_rules[0].class_name == "car"

    def test_recent_events_tracking(self):
        """Orchestrator tracks recent events."""
        orch = CentralOrchestrator(Path("models/test"))
        assert orch.get_recent_events() == []

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self):
        """Event subscription works."""
        orch = CentralOrchestrator(Path("models/test"))
        q = orch.subscribe()
        assert q in orch._event_listeners
        orch.unsubscribe(q)
        assert q not in orch._event_listeners
