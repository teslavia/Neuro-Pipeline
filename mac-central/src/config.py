"""Unified configuration loader for central server."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from src.exceptions import ConfigError


@dataclass
class VLMRuleConfig:
    class_name: str = "person"
    min_confidence: float = 0.8
    prompt_template: str = "person_behavior"


@dataclass
class VLMModelConfig:
    """Configuration for a single VLM model variant."""
    model_id: str = ""
    model_path: str = ""
    is_default: bool = False


@dataclass
class CentralConfig:
    host: str = "0.0.0.0"
    port: int = 50051
    model_path: str = "models/Llama-3.2-3B-Instruct"
    max_message_size_mb: int = 16
    vlm_model_path: str = ""
    inference_mode: str = "llm"  # "llm" or "vlm"
    vlm_models: List["VLMModelConfig"] = field(default_factory=list)


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
    routes: List["AlertRouteConfig"] = field(default_factory=list)


@dataclass
class AlertRuleConfig:
    name: str = ""
    cooldown_seconds: float = 300.0
    severity: str = "critical"


@dataclass
class AlertRouteConfig:
    severity: str = "critical"
    webhook_url: str = ""


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
class RateLimitingConfig:
    enabled: bool = False
    max_rps: int = 100
    burst: int = 20


@dataclass
class ModelManagementConfig:
    enabled: bool = False
    max_models_per_device: int = 3


@dataclass
class ReasoningConfig:
    enabled: bool = False
    max_steps: int = 3
    timeout_per_step: float = 15.0


@dataclass
class RAGConfig:
    enabled: bool = False
    max_history_items: int = 10
    time_window_hours: float = 24.0


@dataclass
class ABTestConfig:
    enabled: bool = False
    traffic_split: float = 0.5
    min_samples: int = 100
    metric: str = "accuracy"


@dataclass
class AnomalyConfig:
    enabled: bool = False
    baseline_window_hours: float = 168.0
    z_score_threshold: float = 3.0
    min_samples: int = 50


@dataclass
class ReIDConfig:
    """Configuration for cross-camera re-identification."""
    enabled: bool = False
    similarity_threshold: float = 0.85
    time_window_seconds: float = 300.0


@dataclass
class TimeSeriesConfig:
    """Configuration for time series analysis."""
    enabled: bool = False
    aggregation_interval: int = 60  # seconds


@dataclass
class AutoAnnotatorConfig:
    """Configuration for auto-annotation."""
    enabled: bool = False
    min_confidence: float = 0.9
    output_dir: str = "data/annotations"


@dataclass
class ReportingConfig:
    """Configuration for report generation."""
    enabled: bool = False
    output_dir: str = "data/reports"
    schedule_hours: float = 24.0


@dataclass
class VLMConfigGuideConfig:
    """Configuration for VLM-guided edge configuration.

    Enables closed-loop optimization where VLM analysis results
    are used to automatically adjust edge device parameters.
    """
    enabled: bool = False
    min_confidence: float = 0.7
    max_adjustments_per_result: int = 3
    auto_apply: bool = False
    enable_region_adjustment: bool = True
    enable_sensitivity_adjustment: bool = True
    enable_fps_adjustment: bool = False


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
    rate_limiting: RateLimitingConfig = field(default_factory=RateLimitingConfig)
    model_management: ModelManagementConfig = field(default_factory=ModelManagementConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    ab_test: ABTestConfig = field(default_factory=ABTestConfig)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    reid: ReIDConfig = field(default_factory=ReIDConfig)
    timeseries: TimeSeriesConfig = field(default_factory=TimeSeriesConfig)
    auto_annotator: AutoAnnotatorConfig = field(default_factory=AutoAnnotatorConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    vlm_config_guide: VLMConfigGuideConfig = field(default_factory=VLMConfigGuideConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """Load config from YAML file, falling back to defaults."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        from src.core.config_loader import load_dataclass_from_dict
        cfg = load_dataclass_from_dict(cls, data)

        # Preserve default VLM rule when YAML has no vlm_rules key
        if "vlm_rules" not in data:
            cfg.vlm_rules = [VLMRuleConfig()]

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
