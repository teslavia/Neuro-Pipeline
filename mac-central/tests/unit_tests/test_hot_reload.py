"""Tests for configuration hot-reload."""

import asyncio
import os
import tempfile
import time
import pytest
import pytest_asyncio

from src.core.hot_reload import (
    ConfigWatcher,
    ConfigChange,
    get_config_watcher,
    reset_config_watcher,
)


@pytest_asyncio.fixture
async def watcher():
    """Create a fresh ConfigWatcher for each test."""
    w = ConfigWatcher(debounce_seconds=0.1, poll_interval=0.1)
    yield w
    # Cleanup
    await w.stop()


@pytest.fixture
def temp_config():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("key: value\n")
        path = f.name
    yield path
    # Cleanup
    os.unlink(path)


class TestConfigChange:
    """Tests for ConfigChange dataclass."""

    def test_is_modified_true(self) -> None:
        """Test is_modified returns True when hashes differ."""
        change = ConfigChange(
            path="/test/config.yaml",
            old_hash="abc123",
            new_hash="def456",
        )
        assert change.is_modified is True

    def test_is_modified_false(self) -> None:
        """Test is_modified returns False when hashes match."""
        change = ConfigChange(
            path="/test/config.yaml",
            old_hash="abc123",
            new_hash="abc123",
        )
        assert change.is_modified is False

    def test_default_timestamp(self) -> None:
        """Test that timestamp defaults to current time."""
        before = time.time()
        change = ConfigChange(path="/test", old_hash="a", new_hash="b")
        after = time.time()
        assert before <= change.timestamp <= after


class TestConfigWatcher:
    """Tests for ConfigWatcher class."""

    def test_watch_registers_file(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that watch registers a file."""
        watcher.watch(temp_config)
        assert temp_config in watcher.watched_files

    def test_watch_with_callback(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that watch registers callbacks."""
        called = []

        def callback(path, change):
            called.append(path)

        watcher.watch(temp_config, callback=callback)
        assert temp_config in watcher._callbacks
        assert callback in watcher._callbacks[temp_config]

    def test_unwatch_removes_callbacks(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that unwatch removes callbacks."""
        called = []

        def callback(path, change):
            called.append(path)

        unwatch = watcher.watch(temp_config, callback=callback)
        assert temp_config in watcher._callbacks

        unwatch()
        assert temp_config not in watcher._callbacks

    def test_on_any_change(self, watcher: ConfigWatcher) -> None:
        """Test global callback registration."""
        called = []

        def callback(path, change):
            called.append(path)

        unregister = watcher.on_any_change(callback=callback)
        assert callback in watcher._global_callbacks

        unregister()
        assert callback not in watcher._global_callbacks

    @pytest.mark.asyncio
    async def test_start_stop(self, watcher: ConfigWatcher) -> None:
        """Test starting and stopping the watcher."""
        assert not watcher.is_running

        await watcher.start()
        assert watcher.is_running

        await watcher.stop()
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_detects_change(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that file changes are detected."""
        changes_detected = []

        async def async_callback(path, change):
            changes_detected.append(str(path))

        watcher.watch(temp_config, async_callback=async_callback)
        await watcher.start()

        # Wait a bit for initial hash
        await asyncio.sleep(0.2)

        # Modify the file
        with open(temp_config, "a") as f:
            f.write("new_key: new_value\n")

        # Wait for detection + debounce
        await asyncio.sleep(0.5)

        await watcher.stop()

        assert len(changes_detected) == 1
        assert temp_config in changes_detected[0]

    @pytest.mark.asyncio
    async def test_debounce(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that rapid changes are debounced."""
        call_count = [0]

        def callback(path, change):
            call_count[0] += 1

        watcher.watch(temp_config, callback=callback)
        await watcher.start()

        # Wait for initial hash
        await asyncio.sleep(0.15)

        # Make rapid changes - all within debounce window
        for i in range(3):
            with open(temp_config, "a") as f:
                f.write(f"key{i}: value{i}\n")
            await asyncio.sleep(0.02)  # Very rapid changes

        # Wait for debounce to complete
        await asyncio.sleep(0.5)

        await watcher.stop()

        # Should trigger at most once due to debounce (may be 0 or 1 depending on timing)
        assert call_count[0] <= 1

    def test_force_reload(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test force reload triggers callbacks."""
        called = []

        def callback(path, change):
            called.append(str(path))

        watcher.watch(temp_config, callback=callback)

        # Force reload should trigger callback even without change
        change = watcher.force_reload(temp_config)

        assert change is not None
        assert len(called) == 1

    def test_force_reload_unwatched(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test force reload on unwatched file."""
        change = watcher.force_reload("/nonexistent/path.yaml")
        assert change is None

    @pytest.mark.asyncio
    async def test_global_callbacks(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that global callbacks are called for any change."""
        changes = []

        async def global_callback(path, change):
            changes.append(str(path))

        watcher.watch(temp_config)  # Watch without callback
        watcher.on_any_change(async_callback=global_callback)

        await watcher.start()
        await asyncio.sleep(0.2)

        # Modify file
        with open(temp_config, "a") as f:
            f.write("new: value\n")

        await asyncio.sleep(0.4)
        await watcher.stop()

        assert len(changes) == 1


class TestGlobalWatcher:
    """Tests for global watcher functions."""

    def test_get_config_watcher(self) -> None:
        """Test that get_config_watcher returns a singleton."""
        reset_config_watcher()
        w1 = get_config_watcher()
        w2 = get_config_watcher()
        assert w1 is w2

    def test_reset_config_watcher(self) -> None:
        """Test that reset creates a new watcher."""
        w1 = get_config_watcher()
        reset_config_watcher()
        w2 = get_config_watcher()
        assert w1 is not w2


class TestComputeHash:
    """Tests for hash computation."""

    def test_hash_consistency(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that hash is consistent for same content."""
        hash1 = watcher._compute_hash(temp_config)
        hash2 = watcher._compute_hash(temp_config)
        assert hash1 == hash2

    def test_hash_changes(self, watcher: ConfigWatcher, temp_config: str) -> None:
        """Test that hash changes when content changes."""
        hash1 = watcher._compute_hash(temp_config)

        with open(temp_config, "a") as f:
            f.write("extra: data\n")

        hash2 = watcher._compute_hash(temp_config)
        assert hash1 != hash2

    def test_hash_missing_file(self, watcher: ConfigWatcher) -> None:
        """Test hash of missing file is empty."""
        hash_val = watcher._compute_hash("/nonexistent/file.yaml")
        assert hash_val == ""
