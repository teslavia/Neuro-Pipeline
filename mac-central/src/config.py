"""Unified configuration loader for central server."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


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
class AppConfig:
    central: CentralConfig = field(default_factory=CentralConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    tls: TLSConfig = field(default_factory=TLSConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    vlm_rules: List[VLMRuleConfig] = field(default_factory=lambda: [VLMRuleConfig()])

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
        return cfg
