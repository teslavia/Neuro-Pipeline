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


@dataclass
class LoggingConfig:
    level: str = "info"
    format: str = "text"
    trace_enabled: bool = True


@dataclass
class AppConfig:
    central: CentralConfig = field(default_factory=CentralConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
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
        )
        lg = data.get("logging", {})
        cfg.logging = LoggingConfig(
            level=lg.get("level", cfg.logging.level),
            format=lg.get("format", cfg.logging.format),
            trace_enabled=bool(lg.get("trace_enabled", cfg.logging.trace_enabled)),
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
