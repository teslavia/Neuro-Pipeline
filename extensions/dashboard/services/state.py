"""Global state management for dashboard services.

This module provides centralized state management and dependency injection
for the dashboard application. All services can be injected from the central
server process for production use, or run standalone with demo data.
"""

import time
from typing import Any, Optional

from fastapi import WebSocket


# ── In-Memory State ──────────────────────────────────────

events: list[dict] = []
ws_clients: list[WebSocket] = []
start_time: float = time.time()


# ── Injected Services ──────────────────────────────────────

detection_store: Any = None
health_checker: Any = None
session_manager: Any = None
orchestrator: Any = None
ab_test_manager: Any = None
model_registry: Any = None
config_path: Optional[str] = None

# v2: Analytics modules
reid_engine: Any = None
timeseries_engine: Any = None
auto_annotator: Any = None
report_generator: Any = None


# ── Setter Functions ──────────────────────────────────────

def set_detection_store(store: Any) -> None:
    """Inject a DetectionStore instance for history queries."""
    global detection_store
    detection_store = store


def set_health_checker(checker: Any) -> None:
    """Inject a HealthChecker instance for probes."""
    global health_checker
    health_checker = checker


def set_session_manager(manager: Any) -> None:
    """Inject a DeviceSessionManager for multi-device queries."""
    global session_manager
    session_manager = manager


def set_orchestrator(orch: Any) -> None:
    """Inject a CentralOrchestrator for command dispatch."""
    global orchestrator
    orchestrator = orch


def set_ab_test_manager(manager: Any) -> None:
    """Inject an ABTestManager for A/B testing."""
    global ab_test_manager
    ab_test_manager = manager


def set_model_registry(registry: Any) -> None:
    """Inject a ModelRegistry for model management."""
    global model_registry
    model_registry = registry


def set_config_path(path: str) -> None:
    """Set the path to the config.yaml file."""
    global config_path
    config_path = path


def set_reid_engine(engine: Any) -> None:
    """Inject a ReIDEngine for cross-camera tracking."""
    global reid_engine
    reid_engine = engine


def set_timeseries_engine(engine: Any) -> None:
    """Inject a TimeSeriesEngine for trend analysis."""
    global timeseries_engine
    timeseries_engine = engine


def set_auto_annotator(annotator: Any) -> None:
    """Inject an AutoAnnotator for annotation export."""
    global auto_annotator
    auto_annotator = annotator


def set_report_generator(generator: Any) -> None:
    """Inject a ReportGenerator for report creation."""
    global report_generator
    report_generator = generator


def inject_from_central(
    *,
    detection_store: Any = None,
    session_manager: Any = None,
    orchestrator: Any = None,
    health_checker: Any = None,
    ab_test_manager: Any = None,
    model_registry: Any = None,
    config_path: Optional[str] = None,
    reid_engine: Any = None,
    timeseries_engine: Any = None,
    auto_annotator: Any = None,
    report_generator: Any = None,
) -> None:
    """One-call injection from central server process.

    This is the main entry point for the central server to inject
    all required services into the dashboard.

    Usage:
        from extensions.dashboard.services.state import inject_from_central
        inject_from_central(
            detection_store=store,
            session_manager=sessions,
            orchestrator=orch,
            health_checker=checker,
            ab_test_manager=ab_test,
            model_registry=registry,
            config_path="config.yaml",
        )
    """
    if detection_store is not None:
        set_detection_store(detection_store)
    if session_manager is not None:
        set_session_manager(session_manager)
    if orchestrator is not None:
        set_orchestrator(orchestrator)
    if health_checker is not None:
        set_health_checker(health_checker)
    if ab_test_manager is not None:
        set_ab_test_manager(ab_test_manager)
    if model_registry is not None:
        set_model_registry(model_registry)
    if config_path is not None:
        set_config_path(config_path)
    if reid_engine is not None:
        set_reid_engine(reid_engine)
    if timeseries_engine is not None:
        set_timeseries_engine(timeseries_engine)
    if auto_annotator is not None:
        set_auto_annotator(auto_annotator)
    if report_generator is not None:
        set_report_generator(report_generator)
