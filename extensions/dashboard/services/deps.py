"""Dashboard dependency injection — replaces 14 global variables + 14 setter functions."""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket


@dataclass
class DashboardDeps:
    """All injectable services for the dashboard."""
    detection_store: Any = None
    health_checker: Any = None
    session_manager: Any = None
    orchestrator: Any = None
    ab_test_manager: Any = None
    model_registry: Any = None
    config_path: Optional[str] = None
    # v2: Analytics
    reid_engine: Any = None
    timeseries_engine: Any = None
    auto_annotator: Any = None
    report_generator: Any = None
    # v2: Intelligence
    behavior_analyzer: Any = None
    anomaly_baseline: Any = None
    reasoning_chain: Any = None
    rag_retriever: Any = None
    # In-memory state
    events: list = field(default_factory=list)
    ws_clients: list = field(default_factory=list)
    start_time: float = field(default_factory=time.time)


# Singleton instance
_deps = DashboardDeps()


def get_deps() -> DashboardDeps:
    """FastAPI dependency — returns the singleton DashboardDeps."""
    return _deps


def inject_from_central(**kwargs) -> None:
    """One-call injection from central server process. Backward compatible."""
    for key, value in kwargs.items():
        if value is not None and hasattr(_deps, key):
            setattr(_deps, key, value)
