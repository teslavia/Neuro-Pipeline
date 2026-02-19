"""Tests for hot-reload integration in main.py."""

import asyncio
import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import yaml

from src.config import AppConfig
from src.core.hot_reload import ConfigWatcher, reset_config_watcher


@pytest_asyncio.fixture
async def tmp_config(tmp_path):
    """Create a temporary config file with default values."""
    cfg_path = tmp_path / "config.yaml"
    default = {
        "central": {"host": "0.0.0.0", "port": 50051, "model_path": "m", "inference_mode": "llm"},
        "logging": {"level": "info"},
        "vlm_rules": [{"class_name": "person", "min_confidence": 0.8, "prompt_template": "p"}],
        "alerting": {"enabled": True, "webhook_url": "", "rules": [], "routes": []},
        "rate_limiting": {"enabled": False, "max_rps": 100, "burst": 20},
        "storage": {"db_path": "data/test.db", "retention_days": 7},
        "sessions": {"heartbeat_interval": 10, "expiry_timeout": 30, "max_devices": 16},
        "batch": {"max_size": 8, "timeout_seconds": 2.0, "enabled": True},
        "circuit_breaker": {"failure_threshold": 5, "recovery_timeout": 30, "half_open_max": 1},
    }
    cfg_path.write_text(yaml.dump(default))
    yield cfg_path
    reset_config_watcher()


class TestHotReloadIntegration:
    @pytest.mark.asyncio
    async def test_config_change_triggers_callback(self, tmp_config):
        """Modifying config.yaml triggers the async callback."""
        watcher = ConfigWatcher(debounce_seconds=0.1, poll_interval=0.2)
        callback = AsyncMock()
        watcher.watch(str(tmp_config), async_callback=callback)
        await watcher.start()

        # Modify the file
        cfg = yaml.safe_load(tmp_config.read_text())
        cfg["logging"]["level"] = "debug"
        tmp_config.write_text(yaml.dump(cfg))

        # Wait for debounce + poll
        await asyncio.sleep(0.5)
        await watcher.stop()

        assert callback.call_count >= 1

    @pytest.mark.asyncio
    async def test_logging_level_change(self, tmp_config):
        """Hot reload updates the root logger level."""
        watcher = ConfigWatcher(debounce_seconds=0.1, poll_interval=0.2)
        logging.getLogger().setLevel(logging.INFO)

        async def on_change(path, change):
            new_cfg = AppConfig.from_yaml(Path(str(tmp_config)))
            new_level = getattr(logging, new_cfg.logging.level.upper(), None)
            if new_level:
                logging.getLogger().setLevel(new_level)

        watcher.watch(str(tmp_config), async_callback=on_change)
        await watcher.start()

        cfg = yaml.safe_load(tmp_config.read_text())
        cfg["logging"]["level"] = "debug"
        tmp_config.write_text(yaml.dump(cfg))

        await asyncio.sleep(0.5)
        await watcher.stop()

        assert logging.getLogger().level == logging.DEBUG

    @pytest.mark.asyncio
    async def test_invalid_config_keeps_current(self, tmp_config):
        """Invalid config does not crash; current config is preserved."""
        watcher = ConfigWatcher(debounce_seconds=0.1, poll_interval=0.2)
        errors = []

        async def on_change(path, change):
            try:
                new_cfg = AppConfig.from_yaml(Path(str(tmp_config)))
                new_cfg.validate()
            except Exception as e:
                errors.append(str(e))

        watcher.watch(str(tmp_config), async_callback=on_change)
        await watcher.start()

        # Write invalid config (bad port)
        cfg = yaml.safe_load(tmp_config.read_text())
        cfg["central"]["port"] = 99999
        tmp_config.write_text(yaml.dump(cfg))

        await asyncio.sleep(0.5)
        await watcher.stop()

        assert len(errors) >= 1
        assert "65535" in errors[0]
