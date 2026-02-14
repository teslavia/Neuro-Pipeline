"""Retry utilities — async and sync with exponential backoff."""

import asyncio
from typing import Callable, Tuple, Type


async def retry_async(
    coro_fn: Callable,
    max_retries: int = 3,
    backoff: float = 0.5,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    """Call *coro_fn()* with exponential-backoff retries.

    Returns the result on success or raises the last exception.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except exceptions as e:
            last_exc = e
            if attempt == max_retries:
                raise
            await asyncio.sleep(backoff * (2 ** attempt))
    raise last_exc  # pragma: no cover — unreachable


def retry_sync(
    fn: Callable,
    max_retries: int = 3,
    backoff: float = 0.1,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    """Synchronous version for SQLite and other blocking calls."""
    import time

    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except exceptions as e:
            last_exc = e
            if attempt == max_retries:
                raise
            time.sleep(backoff * (2 ** attempt))
    raise last_exc  # pragma: no cover — unreachable
