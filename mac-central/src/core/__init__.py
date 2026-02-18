"""Core module for Neuro-Pipeline central server.

This module provides foundational utilities:
- version: Unified version management
- exceptions: Centralized exception hierarchy
- plugin: Extensible plugin system
- events: Publish-subscribe event bus
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
from .plugin import (
    PluginInfo,
    PipelinePlugin,
    PluginManager,
    get_plugin_manager,
)
from .events import (
    Event,
    EventType,
    EventBus,
    EventHandler,
    get_event_bus,
    reset_event_bus,
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
    # Plugin
    "PluginInfo",
    "PipelinePlugin",
    "PluginManager",
    "get_plugin_manager",
    # Events
    "Event",
    "EventType",
    "EventBus",
    "EventHandler",
    "get_event_bus",
    "reset_event_bus",
]
