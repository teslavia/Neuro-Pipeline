"""Tests for retry utilities."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.observability.retry import retry_async, retry_sync


@pytest.mark.asyncio
async def test_async_success_no_retry():
    fn = AsyncMock(return_value="ok")
    result = await retry_async(fn, max_retries=3, backoff=0.01)
    assert result == "ok"
    assert fn.call_count == 1


@pytest.mark.asyncio
async def test_async_transient_failure():
    fn = AsyncMock(side_effect=[ValueError("fail"), "ok"])
    result = await retry_async(fn, max_retries=3, backoff=0.01, exceptions=(ValueError,))
    assert result == "ok"
    assert fn.call_count == 2


@pytest.mark.asyncio
async def test_async_persistent_failure():
    fn = AsyncMock(side_effect=ValueError("always fail"))
    with pytest.raises(ValueError, match="always fail"):
        await retry_async(fn, max_retries=2, backoff=0.01, exceptions=(ValueError,))
    assert fn.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_async_backoff_timing():
    """Verify exponential backoff adds delay."""
    fn = AsyncMock(side_effect=[ValueError("1"), ValueError("2"), "ok"])
    t0 = asyncio.get_event_loop().time()
    await retry_async(fn, max_retries=3, backoff=0.05, exceptions=(ValueError,))
    elapsed = asyncio.get_event_loop().time() - t0
    # backoff=0.05: attempt1 waits 0.05, attempt2 waits 0.10 → total >= 0.15
    assert elapsed >= 0.1


def test_sync_success_no_retry():
    fn = MagicMock(return_value="ok")
    result = retry_sync(fn, max_retries=3, backoff=0.01)
    assert result == "ok"
    assert fn.call_count == 1


def test_sync_transient_failure():
    fn = MagicMock(side_effect=[OSError("locked"), "ok"])
    result = retry_sync(fn, max_retries=3, backoff=0.01, exceptions=(OSError,))
    assert result == "ok"
    assert fn.call_count == 2


def test_sync_persistent_failure():
    fn = MagicMock(side_effect=OSError("always locked"))
    with pytest.raises(OSError, match="always locked"):
        retry_sync(fn, max_retries=2, backoff=0.01, exceptions=(OSError,))
    assert fn.call_count == 3
