"""Core module for Neuro-Pipeline central server.

This module provides foundational utilities:
- version: Unified version management
"""

from .version import (
    __version__,
    get_version,
    get_name,
    get_milestone,
    get_component_version,
    get_full_info,
)

__all__ = [
    "__version__",
    "get_version",
    "get_name",
    "get_milestone",
    "get_component_version",
    "get_full_info",
]
