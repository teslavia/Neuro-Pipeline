"""Tests for edge event dispatch in CentralOrchestrator.handle_edge_event()."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@dataclass
class FakeEdgeEvent:
    type: int = 1
    description: str = "health"
    device_id: str = "edge-001"
    metadata: Dict[str, str] = field(default_factory=dict)


@pytest.fixture
def orchestrator():
    """Create a minimal CentralOrchestrator for testing."""
    from pipeline.central_orchestrator import CentralOrchestrator
    orch = CentralOrchestrator.__new__(CentralOrchestrator)
    orch._alert_manager = None
    orch._event_count = 0
    return orch


@pytest.mark.asyncio
async def test_health_update_dispatches_metrics(orchestrator):
    """HEALTH_UPDATE events should call update_edge_metrics."""
    event = FakeEdgeEvent(
        type=1,
        device_id="edge-001",
        metadata={"fps": "28.5", "frames_processed": "1000"},
    )
    with patch("pipeline.central_orchestrator.update_edge_metrics") as mock_update:
        await orchestrator.handle_edge_event(event)
        mock_update.assert_called_once_with("edge-001", {"fps": "28.5", "frames_processed": "1000"})


@pytest.mark.asyncio
async def test_system_error_triggers_alert(orchestrator):
    """SYSTEM_ERROR events should fire an alert."""
    mock_alert = AsyncMock()
    mock_alert.check_and_fire = AsyncMock(return_value=True)
    orchestrator._alert_manager = mock_alert

    event = FakeEdgeEvent(
        type=2,
        device_id="edge-002",
        metadata={"error": "NPU overheated"},
    )
    await orchestrator.handle_edge_event(event)
    # Give the created task a chance to run
    await asyncio.sleep(0.05)
    mock_alert.check_and_fire.assert_called_once()
    call_args = mock_alert.check_and_fire.call_args
    assert call_args[0][0] == "edge_system_error"
    assert call_args[0][1]["device_id"] == "edge-002"


@pytest.mark.asyncio
async def test_unknown_event_type_no_crash(orchestrator):
    """Unknown event types should be handled gracefully."""
    event = FakeEdgeEvent(type=99, device_id="edge-003")
    await orchestrator.handle_edge_event(event)
    # No exception = pass


@pytest.mark.asyncio
async def test_empty_metadata_handled(orchestrator):
    """Events with empty metadata should not crash."""
    event = FakeEdgeEvent(type=1, device_id="edge-004", metadata={})
    with patch("pipeline.central_orchestrator.update_edge_metrics") as mock_update:
        await orchestrator.handle_edge_event(event)
        mock_update.assert_called_once_with("edge-004", {})


@pytest.mark.asyncio
async def test_missing_device_id(orchestrator):
    """Events without device_id should still dispatch."""
    event = FakeEdgeEvent(type=1, device_id="", metadata={"fps": "30"})
    with patch("pipeline.central_orchestrator.update_edge_metrics") as mock_update:
        await orchestrator.handle_edge_event(event)
        mock_update.assert_called_once_with("", {"fps": "30"})
