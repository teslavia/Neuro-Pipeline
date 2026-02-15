"""Tests for extended config sections (tracing, batch, sessions, cloud_storage)."""

import pytest
from pathlib import Path

from src.config import AppConfig


@pytest.fixture
def config_yaml(tmp_path):
    """Write a config YAML with all new sections."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
central:
  host: "0.0.0.0"
  port: 50051

tracing:
  enabled: true
  endpoint: "http://otel:4317"
  service_name: "test-service"
  sample_rate: 0.5

batch:
  max_size: 16
  timeout_seconds: 5.0
  enabled: false

sessions:
  heartbeat_interval: 15.0
  expiry_timeout: 60.0
  max_devices: 32

cloud_storage:
  enabled: true
  provider: "minio"
  bucket: "detections"
  prefix: "prod/"
  endpoint_url: "http://minio:9000"
  region: "us-west-2"
""")
    return cfg


class TestConfigExtended:
    def test_tracing_config(self, config_yaml):
        cfg = AppConfig.from_yaml(config_yaml)
        assert cfg.tracing.enabled is True
        assert cfg.tracing.endpoint == "http://otel:4317"
        assert cfg.tracing.service_name == "test-service"
        assert cfg.tracing.sample_rate == 0.5

    def test_batch_config(self, config_yaml):
        cfg = AppConfig.from_yaml(config_yaml)
        assert cfg.batch.max_size == 16
        assert cfg.batch.timeout_seconds == 5.0
        assert cfg.batch.enabled is False

    def test_sessions_config(self, config_yaml):
        cfg = AppConfig.from_yaml(config_yaml)
        assert cfg.sessions.heartbeat_interval == 15.0
        assert cfg.sessions.expiry_timeout == 60.0
        assert cfg.sessions.max_devices == 32

    def test_cloud_storage_config(self, config_yaml):
        cfg = AppConfig.from_yaml(config_yaml)
        assert cfg.cloud_storage.enabled is True
        assert cfg.cloud_storage.provider == "minio"
        assert cfg.cloud_storage.bucket == "detections"
        assert cfg.cloud_storage.prefix == "prod/"
        assert cfg.cloud_storage.endpoint_url == "http://minio:9000"
        assert cfg.cloud_storage.region == "us-west-2"

    def test_defaults_when_sections_missing(self, tmp_path):
        cfg_file = tmp_path / "minimal.yaml"
        cfg_file.write_text("central:\n  port: 50051\n")
        cfg = AppConfig.from_yaml(cfg_file)
        assert cfg.tracing.enabled is False
        assert cfg.batch.max_size == 8
        assert cfg.sessions.max_devices == 16
        assert cfg.cloud_storage.enabled is False

    def test_nonexistent_file_returns_defaults(self, tmp_path):
        cfg = AppConfig.from_yaml(tmp_path / "nope.yaml")
        assert cfg.tracing.endpoint == "http://localhost:4317"
        assert cfg.batch.timeout_seconds == 2.0
