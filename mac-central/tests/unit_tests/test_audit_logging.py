"""Tests for control command audit logging."""

import logging
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@dataclass
class FakeCommand:
    type: str = "SET_FPS"
    command_id: str = "cmd-001"
    device_id: str = "edge-001"


@pytest.fixture
def servicer():
    from communication.grpc_server import NeuroPipelineServicer
    mock_orch = AsyncMock()
    svc = NeuroPipelineServicer(mock_orch)
    return svc


@pytest.mark.asyncio
async def test_command_audit_logged(servicer, caplog):
    """Control commands should produce an AUDIT log entry."""
    ctx = AsyncMock()
    with caplog.at_level(logging.INFO):
        with patch("communication.grpc_server.neuro_pipeline_pb2") as mock_pb2:
            mock_pb2.CommandResponse.return_value = MagicMock()
            await servicer.SendControlCommand(FakeCommand(), ctx)
    assert any("AUDIT" in r.message for r in caplog.records)
    assert any("cmd-001" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_command_metrics_incremented(servicer):
    """Control commands should increment the counter."""
    ctx = AsyncMock()
    with patch("communication.grpc_server.control_commands_total") as mock_counter:
        mock_label = MagicMock()
        mock_counter.labels.return_value = mock_label
        with patch("communication.grpc_server.neuro_pipeline_pb2") as mock_pb2:
            mock_pb2.CommandResponse.return_value = MagicMock()
            await servicer.SendControlCommand(FakeCommand(), ctx)
        mock_counter.labels.assert_called_once()
        mock_label.inc.assert_called_once()


@pytest.mark.asyncio
async def test_audit_log_format(servicer, caplog):
    """Audit log should contain command_type, command_id, device_id."""
    ctx = AsyncMock()
    with caplog.at_level(logging.INFO):
        with patch("communication.grpc_server.neuro_pipeline_pb2") as mock_pb2:
            mock_pb2.CommandResponse.return_value = MagicMock()
            await servicer.SendControlCommand(FakeCommand(type="SHUTDOWN", command_id="cmd-002", device_id="edge-002"), ctx)
    audit_msgs = [r.message for r in caplog.records if "AUDIT" in r.message]
    assert len(audit_msgs) >= 1
    assert "SHUTDOWN" in audit_msgs[0]
    assert "cmd-002" in audit_msgs[0]
