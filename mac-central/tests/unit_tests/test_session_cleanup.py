"""Tests for session cleanup loop in main.py."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from communication.device_session import DeviceSessionManager


async def _session_cleanup_loop_under_test(session_mgr, expiry_timeout, gauge):
    """Replica of main._session_cleanup_loop for testing without import side effects."""
    interval = max(expiry_timeout / 2, 0.05)
    while True:
        try:
            await asyncio.sleep(interval)
            expired = session_mgr.cleanup_expired()
            for device_id in expired:
                gauge.labels(device_id=device_id).set(0)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


@pytest.mark.asyncio
async def test_cleanup_loop_triggers_periodically():
    """Cleanup loop should call cleanup_expired at regular intervals."""
    mgr = DeviceSessionManager(expiry_timeout=0.2)
    mgr.register("dev-1")
    mgr._sessions["dev-1"].last_heartbeat = time.time() - 1.0

    mock_gauge = MagicMock()
    mock_gauge.labels.return_value = MagicMock()

    task = asyncio.create_task(
        _session_cleanup_loop_under_test(mgr, expiry_timeout=0.2, gauge=mock_gauge)
    )
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert mgr.get_session("dev-1") is None


@pytest.mark.asyncio
async def test_cleanup_loop_updates_gauge():
    """Expired devices should have their gauge set to 0."""
    mgr = DeviceSessionManager(expiry_timeout=0.2)
    mgr.register("dev-gauge")
    mgr._sessions["dev-gauge"].last_heartbeat = time.time() - 1.0

    mock_gauge = MagicMock()
    mock_label = MagicMock()
    mock_gauge.labels.return_value = mock_label

    task = asyncio.create_task(
        _session_cleanup_loop_under_test(mgr, expiry_timeout=0.2, gauge=mock_gauge)
    )
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    mock_gauge.labels.assert_called_with(device_id="dev-gauge")
    mock_label.set.assert_called_with(0)


@pytest.mark.asyncio
async def test_cleanup_loop_cancels_cleanly():
    """Cleanup loop should exit cleanly on cancellation."""
    mgr = DeviceSessionManager(expiry_timeout=10.0)
    mock_gauge = MagicMock()
    task = asyncio.create_task(
        _session_cleanup_loop_under_test(mgr, expiry_timeout=10.0, gauge=mock_gauge)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
