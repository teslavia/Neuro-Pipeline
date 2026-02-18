"""Plugin system for Neuro-Pipeline.

Provides an extensible plugin architecture for custom processing
pipelines and event handlers.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Metadata about a plugin."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    priority: int = 100  # Lower = higher priority
    enabled: bool = True


class PipelinePlugin(ABC):
    """Base class for Neuro-Pipeline plugins.

    Plugins can hook into various stages of the detection pipeline
    to add custom processing, filtering, or event handling.
    """

    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        pass

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the plugin with configuration.

        Args:
            config: Plugin-specific configuration from config.yaml
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up plugin resources."""
        pass

    async def process_detection(self, detection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single detection. Return None to filter out.

        Override this method to implement detection filtering or enrichment.

        Args:
            detection: Detection dict with class_name, confidence, bbox, etc.

        Returns:
            Modified detection dict, or None to filter out.
        """
        return detection

    async def process_frame(self, frame_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a full frame with all detections.

        Override this method to implement frame-level processing.

        Args:
            frame_data: Full frame dict with detections, metadata, etc.

        Returns:
            Modified frame dict, or None to skip.
        """
        return frame_data

    async def on_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle an event from the event bus.

        Override this method to react to system events.

        Args:
            event_type: Event type string
            event_data: Event payload
        """
        pass


class PluginManager:
    """Manages plugin lifecycle and execution.

    Plugins are registered, initialized, and invoked in priority order.
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PipelinePlugin] = {}
        self._initialized: bool = False

    def register(self, plugin: PipelinePlugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: PipelinePlugin instance

        Raises:
            ValueError: If plugin with same name already registered
        """
        name = plugin.info.name
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' already registered")
        self._plugins[name] = plugin
        logger.info(f"Plugin registered: {name} v{plugin.info.version}")

    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if plugin was removed, False if not found
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Plugin unregistered: {name}")
            return True
        return False

    def get_plugin(self, name: str) -> Optional[PipelinePlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        """List all registered plugins."""
        return [p.info for p in self._plugins.values()]

    async def initialize_all(self, configs: Dict[str, Dict[str, Any]]) -> None:
        """Initialize all registered plugins.

        Args:
            configs: Dict mapping plugin name to its config
        """
        if self._initialized:
            logger.warning("Plugins already initialized")
            return

        # Sort by priority (lower = higher priority)
        sorted_plugins = sorted(
            self._plugins.items(),
            key=lambda x: x[1].info.priority
        )

        for name, plugin in sorted_plugins:
            if not plugin.info.enabled:
                logger.info(f"Skipping disabled plugin: {name}")
                continue

            config = configs.get(name, {})
            try:
                await plugin.initialize(config)
                logger.info(f"Plugin initialized: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize plugin '{name}': {e}")
                if plugin.info.priority < 50:  # Critical plugin
                    raise

        self._initialized = True

    async def shutdown_all(self) -> None:
        """Shutdown all plugins in reverse priority order."""
        sorted_plugins = sorted(
            self._plugins.items(),
            key=lambda x: x[1].info.priority,
            reverse=True
        )

        for name, plugin in sorted_plugins:
            try:
                await plugin.shutdown()
                logger.info(f"Plugin shutdown: {name}")
            except Exception as e:
                logger.warning(f"Error shutting down plugin '{name}': {e}")

        self._initialized = False

    async def process_detection(self, detection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run detection through all plugins.

        Args:
            detection: Detection dict

        Returns:
            Processed detection, or None if filtered out
        """
        result = detection
        for plugin in sorted(self._plugins.values(), key=lambda p: p.info.priority):
            if not plugin.info.enabled:
                continue
            try:
                result = await plugin.process_detection(result)
                if result is None:
                    return None  # Filtered out
            except Exception as e:
                logger.warning(f"Plugin '{plugin.info.name}' error in process_detection: {e}")
        return result

    async def process_frame(self, frame_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run frame through all plugins.

        Args:
            frame_data: Frame dict

        Returns:
            Processed frame, or None if filtered out
        """
        result = frame_data
        for plugin in sorted(self._plugins.values(), key=lambda p: p.info.priority):
            if not plugin.info.enabled:
                continue
            try:
                result = await plugin.process_frame(result)
                if result is None:
                    return None  # Filtered out
            except Exception as e:
                logger.warning(f"Plugin '{plugin.info.name}' error in process_frame: {e}")
        return result

    async def emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Emit an event to all plugins.

        Args:
            event_type: Event type string
            event_data: Event payload
        """
        for plugin in self._plugins.values():
            if not plugin.info.enabled:
                continue
            try:
                await plugin.on_event(event_type, event_data)
            except Exception as e:
                logger.warning(f"Plugin '{plugin.info.name}' error in on_event: {e}")


# Global plugin manager instance
_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
