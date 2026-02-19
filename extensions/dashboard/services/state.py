"""Global state management — delegates to DashboardDeps singleton.

Backward-compatible: all existing imports (events, set_detection_store, inject_from_central, etc.)
continue to work. New code should use `from ..services.deps import get_deps` with FastAPI Depends.
"""

from typing import Any, Optional

from .deps import _deps, inject_from_central  # noqa: F401 — re-export


# ── Mutable aliases (bound to deps singleton's lists) ──
events = _deps.events
ws_clients = _deps.ws_clients
start_time = _deps.start_time


# ── Property-style accessors for injected services ──
# Module-level variables can't be properties, so routers that do
# `from ...services import state; state.detection_store` get live values.

def __getattr__(name: str):
    """Module-level __getattr__ for lazy access to deps fields."""
    if hasattr(_deps, name):
        return getattr(_deps, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Setter functions (backward compat) ──

def set_detection_store(store: Any) -> None:
    _deps.detection_store = store

def set_health_checker(checker: Any) -> None:
    _deps.health_checker = checker

def set_session_manager(manager: Any) -> None:
    _deps.session_manager = manager

def set_orchestrator(orch: Any) -> None:
    _deps.orchestrator = orch

def set_ab_test_manager(manager: Any) -> None:
    _deps.ab_test_manager = manager

def set_model_registry(registry: Any) -> None:
    _deps.model_registry = registry

def set_config_path(path: str) -> None:
    _deps.config_path = path

def set_reid_engine(engine: Any) -> None:
    _deps.reid_engine = engine

def set_timeseries_engine(engine: Any) -> None:
    _deps.timeseries_engine = engine

def set_auto_annotator(annotator: Any) -> None:
    _deps.auto_annotator = annotator

def set_report_generator(generator: Any) -> None:
    _deps.report_generator = generator

def set_behavior_analyzer(analyzer: Any) -> None:
    _deps.behavior_analyzer = analyzer

def set_anomaly_baseline(baseline: Any) -> None:
    _deps.anomaly_baseline = baseline

def set_reasoning_chain(chain: Any) -> None:
    _deps.reasoning_chain = chain

def set_rag_retriever(retriever: Any) -> None:
    _deps.rag_retriever = retriever
