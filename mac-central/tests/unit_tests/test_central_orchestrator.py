"""Unit tests for CentralOrchestrator."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.application_logic.central_orchestrator import (
    CentralOrchestrator,
    VLMTriggerRule,
)


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
