"""Configuration hot-reload for Neuro-Pipeline.

Monitors configuration files for changes and triggers callbacks
when updates are detected.
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """Represents a detected configuration change."""
    path: str
    old_hash: str
    new_hash: str
    timestamp: float = field(default_factory=time.time)

    @property
    def is_modified(self) -> bool:
        return self.old_hash != self.new_hash


ConfigCallback = Callable[[Path, ConfigChange], None]


class ConfigWatcher:
    """Watches configuration files for changes and triggers callbacks.

    Supports:
    - Multiple file watching
    - Debounced change detection
    - Sync and async callbacks
    - Graceful error handling
    """

    def __init__(
        self,
        debounce_seconds: float = 1.0,
        poll_interval: float = 5.0,
    ) -> None:
        """Initialize the config watcher.

        Args:
            debounce_seconds: Wait time after change before triggering callbacks
            poll_interval: How often to check for file changes
        """
        self._debounce_seconds = debounce_seconds
        self._poll_interval = poll_interval

        self._watched_files: Dict[str, str] = {}  # path -> last_hash
        self._callbacks: Dict[str, List[ConfigCallback]] = {}
        self._async_callbacks: Dict[str, List[Callable[[Path, ConfigChange], Any]]] = {}
        self._global_callbacks: List[ConfigCallback] = []
        self._global_async_callbacks: List[Callable[[Path, ConfigChange], Any]] = []

        self._pending_changes: Dict[str, float] = {}  # path -> first_change_time
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    def _compute_hash(self, path: str) -> str:
        """Compute MD5 hash of file contents."""
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            return ""
        except Exception as e:
            logger.warning(f"Error reading {path}: {e}")
            return ""

    def watch(
        self,
        path: str,
        callback: Optional[ConfigCallback] = None,
        async_callback: Optional[Callable[[Path, ConfigChange], Any]] = None,
    ) -> Callable[[], None]:
        """Watch a configuration file for changes.

        Args:
            path: Path to configuration file
            callback: Sync callback to call on change (optional)
            async_callback: Async callback to call on change (optional)

        Returns:
            Unwatch function
        """
        path = os.path.abspath(path)

        # Initialize hash
        if path not in self._watched_files:
            self._watched_files[path] = self._compute_hash(path)
            self._callbacks[path] = []
            self._async_callbacks[path] = []
            logger.info(f"Watching config file: {path}")

        # Register callbacks
        if callback:
            self._callbacks[path].append(callback)
        if async_callback:
            self._async_callbacks[path].append(async_callback)

        def unwatch():
            if callback and callback in self._callbacks.get(path, []):
                self._callbacks[path].remove(callback)
            if async_callback and async_callback in self._async_callbacks.get(path, []):
                self._async_callbacks[path].remove(async_callback)
            # Remove from watched if no callbacks left
            if not self._callbacks.get(path) and not self._async_callbacks.get(path):
                self._watched_files.pop(path, None)
                self._callbacks.pop(path, None)
                self._async_callbacks.pop(path, None)
                logger.debug(f"Stopped watching: {path}")

        return unwatch

    def on_any_change(
        self,
        callback: Optional[ConfigCallback] = None,
        async_callback: Optional[Callable[[Path, ConfigChange], Any]] = None,
    ) -> Callable[[], None]:
        """Register a callback for any watched file change.

        Args:
            callback: Sync callback (optional)
            async_callback: Async callback (optional)

        Returns:
            Unregister function
        """
        registered = []

        if callback:
            self._global_callbacks.append(callback)
            registered.append(callback)

        if async_callback:
            self._global_async_callbacks.append(async_callback)
            registered.append(async_callback)

        def unregister():
            for cb in registered:
                if cb in self._global_callbacks:
                    self._global_callbacks.remove(cb)
                if cb in self._global_async_callbacks:
                    self._global_async_callbacks.remove(cb)

        return unregister

    async def start(self) -> None:
        """Start watching for changes."""
        if self._running:
            logger.warning("ConfigWatcher already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(
            f"ConfigWatcher started: {len(self._watched_files)} files, "
            f"poll_interval={self._poll_interval}s, debounce={self._debounce_seconds}s"
        )

    async def stop(self) -> None:
        """Stop watching for changes."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ConfigWatcher stopped")

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        while self._running:
            try:
                await self._check_changes()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
                await asyncio.sleep(self._poll_interval)

    async def _check_changes(self) -> None:
        """Check all watched files for changes."""
        now = time.time()

        for path in list(self._watched_files.keys()):
            old_hash = self._watched_files[path]
            new_hash = self._compute_hash(path)

            if new_hash != old_hash:
                # Track first change time
                if path not in self._pending_changes:
                    self._pending_changes[path] = now
                    logger.debug(f"Change detected in {path}, debouncing...")

                # Check if debounce period has passed
                first_change = self._pending_changes[path]
                if now - first_change >= self._debounce_seconds:
                    change = ConfigChange(
                        path=path,
                        old_hash=old_hash,
                        new_hash=new_hash,
                    )
                    await self._handle_change(Path(path), change)
                    self._watched_files[path] = new_hash
                    del self._pending_changes[path]

    async def _handle_change(self, path: Path, change: ConfigChange) -> None:
        """Handle a configuration change."""
        logger.info(f"Config changed: {path}")

        # Call file-specific callbacks
        path_str = str(path)
        for callback in self._callbacks.get(path_str, []):
            try:
                callback(path, change)
            except Exception as e:
                logger.warning(f"Config callback error for {path}: {e}")

        # Call file-specific async callbacks
        for callback in self._async_callbacks.get(path_str, []):
            try:
                await callback(path, change)
            except Exception as e:
                logger.warning(f"Async config callback error for {path}: {e}")

        # Call global callbacks
        for callback in self._global_callbacks:
            try:
                callback(path, change)
            except Exception as e:
                logger.warning(f"Global config callback error: {e}")

        # Call global async callbacks
        for callback in self._global_async_callbacks:
            try:
                await callback(path, change)
            except Exception as e:
                logger.warning(f"Global async config callback error: {e}")

    def force_reload(self, path: str) -> Optional[ConfigChange]:
        """Force a reload of a specific config file.

        Triggers all callbacks even if content hasn't changed.

        Args:
            path: Path to configuration file

        Returns:
            ConfigChange if file exists, None otherwise
        """
        path = os.path.abspath(path)
        if path not in self._watched_files:
            logger.warning(f"Cannot force reload unwatched file: {path}")
            return None

        old_hash = self._watched_files[path]
        new_hash = self._compute_hash(path)

        change = ConfigChange(path=path, old_hash=old_hash, new_hash=new_hash)
        self._watched_files[path] = new_hash

        # Trigger callbacks synchronously
        for callback in self._callbacks.get(path, []):
            try:
                callback(Path(path), change)
            except Exception as e:
                logger.warning(f"Config callback error for {path}: {e}")

        for callback in self._global_callbacks:
            try:
                callback(Path(path), change)
            except Exception as e:
                logger.warning(f"Global config callback error: {e}")

        return change

    @property
    def watched_files(self) -> List[str]:
        """List of watched file paths."""
        return list(self._watched_files.keys())

    @property
    def is_running(self) -> bool:
        """Whether the watcher is running."""
        return self._running


# Global config watcher instance
_watcher: Optional[ConfigWatcher] = None


def get_config_watcher() -> ConfigWatcher:
    """Get the global config watcher instance."""
    global _watcher
    if _watcher is None:
        _watcher = ConfigWatcher()
    return _watcher


def reset_config_watcher() -> None:
    """Reset the global config watcher (for testing)."""
    global _watcher
    if _watcher is not None:
        # Try to stop the watcher if there's a running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_watcher.stop())
        except RuntimeError:
            # No running loop, just set to None
            pass
    _watcher = None
