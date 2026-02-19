"""Unified logger factory — replaces repeated try/except structlog blocks."""

import logging


def get_logger(name: str):
    """Get a logger, preferring structlog if available.

    Replaces the 8+ occurrences of:
        try:
            import structlog
            logger = structlog.get_logger(__name__)
        except ImportError:
            logger = logging.getLogger(__name__)
    """
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
