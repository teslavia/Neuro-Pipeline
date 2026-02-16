"""Tests for AppConfig.validate()."""

import pytest

from src.config import AppConfig
from src.exceptions import ConfigError


class TestConfigValidation:
    def test_default_config_valid(self):
        cfg = AppConfig()
        cfg.validate()  # should not raise

    def test_port_zero_invalid(self):
        cfg = AppConfig()
        cfg.central.port = 0
        with pytest.raises(ConfigError, match="central.port"):
            cfg.validate()

    def test_port_too_high(self):
        cfg = AppConfig()
        cfg.metrics.port = 70000
        with pytest.raises(ConfigError, match="metrics.port"):
            cfg.validate()

    def test_port_valid_boundary(self):
        cfg = AppConfig()
        cfg.central.port = 1
        cfg.metrics.port = 65535
        cfg.validate()

    def test_confidence_negative(self):
        cfg = AppConfig()
        cfg.vlm_rules[0].min_confidence = -0.1
        with pytest.raises(ConfigError, match="min_confidence"):
            cfg.validate()

    def test_confidence_above_one(self):
        cfg = AppConfig()
        cfg.vlm_rules[0].min_confidence = 1.5
        with pytest.raises(ConfigError, match="min_confidence"):
            cfg.validate()

    def test_confidence_boundary_valid(self):
        cfg = AppConfig()
        cfg.vlm_rules[0].min_confidence = 0.0
        cfg.validate()
        cfg.vlm_rules[0].min_confidence = 1.0
        cfg.validate()

    def test_timeout_zero_invalid(self):
        cfg = AppConfig()
        cfg.circuit_breaker.recovery_timeout = 0
        with pytest.raises(ConfigError, match="recovery_timeout"):
            cfg.validate()

    def test_timeout_negative_invalid(self):
        cfg = AppConfig()
        cfg.sessions.expiry_timeout = -1
        with pytest.raises(ConfigError, match="expiry_timeout"):
            cfg.validate()

    def test_batch_timeout_zero(self):
        cfg = AppConfig()
        cfg.batch.timeout_seconds = 0
        with pytest.raises(ConfigError, match="batch.timeout_seconds"):
            cfg.validate()

    def test_tls_missing_cert(self, tmp_path):
        cfg = AppConfig()
        cfg.tls.enabled = True
        cfg.tls.ca_cert = str(tmp_path / "nonexistent.pem")
        with pytest.raises(ConfigError, match="tls.ca_cert"):
            cfg.validate()

    def test_tls_valid_certs(self, tmp_path):
        for name in ("ca.pem", "server.pem", "server-key.pem"):
            (tmp_path / name).write_text("fake cert")
        cfg = AppConfig()
        cfg.tls.enabled = True
        cfg.tls.ca_cert = str(tmp_path / "ca.pem")
        cfg.tls.server_cert = str(tmp_path / "server.pem")
        cfg.tls.server_key = str(tmp_path / "server-key.pem")
        cfg.validate()

    def test_inference_mode_invalid(self):
        cfg = AppConfig()
        cfg.central.inference_mode = "invalid"
        with pytest.raises(ConfigError, match="inference_mode"):
            cfg.validate()

    def test_inference_mode_vlm_valid(self):
        cfg = AppConfig()
        cfg.central.inference_mode = "vlm"
        cfg.validate()

    def test_max_devices_zero(self):
        cfg = AppConfig()
        cfg.sessions.max_devices = 0
        with pytest.raises(ConfigError, match="max_devices"):
            cfg.validate()

    def test_cloud_storage_enabled_no_bucket(self):
        cfg = AppConfig()
        cfg.cloud_storage.enabled = True
        cfg.cloud_storage.bucket = ""
        with pytest.raises(ConfigError, match="bucket"):
            cfg.validate()

    def test_cloud_storage_enabled_with_bucket(self):
        cfg = AppConfig()
        cfg.cloud_storage.enabled = True
        cfg.cloud_storage.bucket = "my-bucket"
        cfg.validate()
