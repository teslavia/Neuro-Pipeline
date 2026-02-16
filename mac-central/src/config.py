"""Unified configuration loader for central server."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from src.exceptions import ConfigError


@dataclass
class VLMRuleConfig:
    class_name: str = "person"
    min_confidence: float = 0.8
    prompt_template: str = "person_behavior"


@dataclass
class CentralConfig:
    host: str = "0.0.0.0"
    port: int = 50051
    model_path: str = "models/Llama-3.2-3B-Instruct"
    max_message_size_mb: int = 16
    vlm_model_path: str = ""
    inference_mode: str = "llm"  # "llm" or "vlm"


@dataclass
class LoggingConfig:
    level: str = "info"
    format: str = "text"
    trace_enabled: bool = True
    file_path: str = ""
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class TLSConfig:
    enabled: bool = False
    ca_cert: str = ""
    server_cert: str = ""
    server_key: str = ""


@dataclass
class StorageConfig:
    db_path: str = "data/detections.db"
    retention_days: int = 7


@dataclass
class MetricsConfig:
    enabled: bool = True
    port: int = 9090


@dataclass
class AlertingConfig:
    enabled: bool = True
    webhook_url: str = ""
    rules: List["AlertRuleConfig"] = field(default_factory=list)


@dataclass
class AlertRuleConfig:
    name: str = ""
    cooldown_seconds: float = 300.0


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max: int = 1


@dataclass
class TracingConfig:
    enabled: bool = False
    endpoint: str = "http://localhost:4317"
    service_name: str = "neuro-pipeline-central"
    sample_rate: float = 1.0


@dataclass
class BatchConfig:
    max_size: int = 8
    timeout_seconds: float = 2.0
    enabled: bool = True


@dataclass
class SessionConfig:
    heartbeat_interval: float = 10.0
    expiry_timeout: float = 30.0
    max_devices: int = 16


@dataclass
class CloudStorageConfig:
    enabled: bool = False
    provider: str = "s3"
    bucket: str = ""
    prefix: str = "neuro-pipeline/"
    endpoint_url: str = ""
    region: str = "us-east-1"


@dataclass
class AppConfig:
    central: CentralConfig = field(default_factory=CentralConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    tls: TLSConfig = field(default_factory=TLSConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    vlm_rules: List[VLMRuleConfig] = field(default_factory=lambda: [VLMRuleConfig()])
    tracing: TracingConfig = field(default_factory=TracingConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    cloud_storage: CloudStorageConfig = field(default_factory=CloudStorageConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """Load config from YAML file, falling back to defaults."""
        cfg = cls()
        if not path.exists():
            return cfg
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        c = data.get("central", {})
        cfg.central = CentralConfig(
            host=c.get("host", cfg.central.host),
            port=int(c.get("port", cfg.central.port)),
            model_path=c.get("model_path", cfg.central.model_path),
            max_message_size_mb=int(c.get("max_message_size_mb", cfg.central.max_message_size_mb)),
            vlm_model_path=c.get("vlm_model_path", cfg.central.vlm_model_path),
            inference_mode=c.get("inference_mode", cfg.central.inference_mode),
        )
        lg = data.get("logging", {})
        cfg.logging = LoggingConfig(
            level=lg.get("level", cfg.logging.level),
            format=lg.get("format", cfg.logging.format),
            trace_enabled=bool(lg.get("trace_enabled", cfg.logging.trace_enabled)),
            file_path=lg.get("file_path", cfg.logging.file_path),
            max_bytes=int(lg.get("max_bytes", cfg.logging.max_bytes)),
            backup_count=int(lg.get("backup_count", cfg.logging.backup_count)),
        )
        tls = data.get("tls", {})
        cfg.tls = TLSConfig(
            enabled=bool(tls.get("enabled", cfg.tls.enabled)),
            ca_cert=tls.get("ca_cert", cfg.tls.ca_cert),
            server_cert=tls.get("server_cert", cfg.tls.server_cert),
            server_key=tls.get("server_key", cfg.tls.server_key),
        )
        st = data.get("storage", {})
        cfg.storage = StorageConfig(
            db_path=st.get("db_path", cfg.storage.db_path),
            retention_days=int(st.get("retention_days", cfg.storage.retention_days)),
        )
        rules_data = data.get("vlm_rules", [])
        if rules_data:
            cfg.vlm_rules = [
                VLMRuleConfig(
                    class_name=r.get("class_name", "person"),
                    min_confidence=float(r.get("min_confidence", 0.8)),
                    prompt_template=r.get("prompt_template", "person_behavior"),
                )
                for r in rules_data
            ]
        mt = data.get("metrics", {})
        cfg.metrics = MetricsConfig(
            enabled=bool(mt.get("enabled", cfg.metrics.enabled)),
            port=int(mt.get("port", cfg.metrics.port)),
        )
        al = data.get("alerting", {})
        cfg.alerting = AlertingConfig(
            enabled=bool(al.get("enabled", cfg.alerting.enabled)),
            webhook_url=al.get("webhook_url", cfg.alerting.webhook_url),
            rules=[
                AlertRuleConfig(
                    name=r.get("name", ""),
                    cooldown_seconds=float(r.get("cooldown_seconds", 300)),
                )
                for r in al.get("rules", [])
            ],
        )
        cb = data.get("circuit_breaker", {})
        cfg.circuit_breaker = CircuitBreakerConfig(
            failure_threshold=int(cb.get("failure_threshold", cfg.circuit_breaker.failure_threshold)),
            recovery_timeout=float(cb.get("recovery_timeout", cfg.circuit_breaker.recovery_timeout)),
            half_open_max=int(cb.get("half_open_max", cfg.circuit_breaker.half_open_max)),
        )
        tr = data.get("tracing", {})
        cfg.tracing = TracingConfig(
            enabled=bool(tr.get("enabled", cfg.tracing.enabled)),
            endpoint=tr.get("endpoint", cfg.tracing.endpoint),
            service_name=tr.get("service_name", cfg.tracing.service_name),
            sample_rate=float(tr.get("sample_rate", cfg.tracing.sample_rate)),
        )
        ba = data.get("batch", {})
        cfg.batch = BatchConfig(
            max_size=int(ba.get("max_size", cfg.batch.max_size)),
            timeout_seconds=float(ba.get("timeout_seconds", cfg.batch.timeout_seconds)),
            enabled=bool(ba.get("enabled", cfg.batch.enabled)),
        )
        se = data.get("sessions", {})
        cfg.sessions = SessionConfig(
            heartbeat_interval=float(se.get("heartbeat_interval", cfg.sessions.heartbeat_interval)),
            expiry_timeout=float(se.get("expiry_timeout", cfg.sessions.expiry_timeout)),
            max_devices=int(se.get("max_devices", cfg.sessions.max_devices)),
        )
        cs = data.get("cloud_storage", {})
        cfg.cloud_storage = CloudStorageConfig(
            enabled=bool(cs.get("enabled", cfg.cloud_storage.enabled)),
            provider=cs.get("provider", cfg.cloud_storage.provider),
            bucket=cs.get("bucket", cfg.cloud_storage.bucket),
            prefix=cs.get("prefix", cfg.cloud_storage.prefix),
            endpoint_url=cs.get("endpoint_url", cfg.cloud_storage.endpoint_url),
            region=cs.get("region", cfg.cloud_storage.region),
        )
        return cfg

    def validate(self) -> None:
        """Validate configuration values. Raises ConfigError on invalid values."""
        # Port ranges
        for name, port in [("central.port", self.central.port),
                           ("metrics.port", self.metrics.port)]:
            if not (1 <= port <= 65535):
                raise ConfigError(f"{name} must be 1-65535, got {port}")

        # Confidence thresholds in VLM rules
        for i, rule in enumerate(self.vlm_rules):
            if not (0.0 <= rule.min_confidence <= 1.0):
                raise ConfigError(
                    f"vlm_rules[{i}].min_confidence must be 0.0-1.0, got {rule.min_confidence}"
                )

        # Positive timeouts
        for name, val in [
            ("circuit_breaker.recovery_timeout", self.circuit_breaker.recovery_timeout),
            ("sessions.expiry_timeout", self.sessions.expiry_timeout),
            ("batch.timeout_seconds", self.batch.timeout_seconds),
        ]:
            if val <= 0:
                raise ConfigError(f"{name} must be > 0, got {val}")

        # TLS cert paths
        if self.tls.enabled:
            for name, path in [("tls.ca_cert", self.tls.ca_cert),
                               ("tls.server_cert", self.tls.server_cert),
                               ("tls.server_key", self.tls.server_key)]:
                if not path or not Path(path).exists():
                    raise ConfigError(f"{name} path does not exist: {path}")

        # Inference mode
        if self.central.inference_mode not in ("llm", "vlm"):
            raise ConfigError(
                f"inference_mode must be 'llm' or 'vlm', got '{self.central.inference_mode}'"
            )

        # Max devices
        if self.sessions.max_devices <= 0:
            raise ConfigError(
                f"sessions.max_devices must be > 0, got {self.sessions.max_devices}"
            )

        # Cloud storage bucket
        if self.cloud_storage.enabled and not self.cloud_storage.bucket:
            raise ConfigError("cloud_storage.bucket must be non-empty when enabled")
