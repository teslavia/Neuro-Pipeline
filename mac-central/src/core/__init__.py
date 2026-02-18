"""Core module for Neuro-Pipeline central server.

This module provides foundational utilities:
- version: Unified version management
- exceptions: Centralized exception hierarchy
"""

from .version import (
    __version__,
    get_version,
    get_name,
    get_milestone,
    get_component_version,
    get_full_info,
)
from .exceptions import (
    NeuroPipelineError,
    ConfigError,
    ModelLoadError,
    InferenceError,
    StorageError,
    CommunicationError,
)

__all__ = [
    # Version
    "__version__",
    "get_version",
    "get_name",
    "get_milestone",
    "get_component_version",
    "get_full_info",
    # Exceptions
    "NeuroPipelineError",
    "ConfigError",
    "ModelLoadError",
    "InferenceError",
    "StorageError",
    "CommunicationError",
]
