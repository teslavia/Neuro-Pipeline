"""Error handling utilities — replaces repeated try-except-log patterns."""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional


def safe_async(operation_name: str, default: Any = None, logger: Optional[logging.Logger] = None):
    """Decorator: wrap an async call, log failures, return default on error.

    Replaces 15+ occurrences of:
        try:
            result = await some_operation(...)
        except Exception as e:
            logger.warning(f"... failed: {e}")

    Usage:
        @safe_async("behavior_analysis")
        async def analyze(self, ...):
            ...
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            _logger = logger
            if _logger is None:
                # Try to get logger from self if it's a method
                if args and hasattr(args[0], '_logger'):
                    _logger = args[0]._logger
                else:
                    _logger = logging.getLogger(fn.__module__)
            try:
                return await fn(*args, **kwargs)
            except asyncio.CancelledError:
                raise  # Never swallow cancellation
            except Exception as e:
                _logger.warning(f"{operation_name} failed: {e}")
                return default
        return wrapper
    return decorator
