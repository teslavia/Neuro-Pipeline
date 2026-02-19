#!/usr/bin/env python3
"""Central server main entry point — wires all subsystems from config."""
import argparse
import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.communication.grpc_server import NeuroPipelineServer
from src.pipeline.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from src.communication.device_session import DeviceSessionManager
from src.config import AppConfig
from src.observability.circuit_breaker import CircuitBreaker
from src.observability.alerting import AlertManager, AlertRule, AlertSeverity, AlertRoute
from src.observability.metrics import edge_device_status
from src.storage.detection_store import DetectionStore
from src.storage.cloud_storage import CloudStorageClient
from src.core import __version__
from src.core.hot_reload import get_config_watcher


def setup_logging(cfg) -> None:
    """Configure logging with optional file rotation."""
    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if cfg.logging.file_path:
        log_path = Path(cfg.logging.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=cfg.logging.max_bytes,
            backupCount=cfg.logging.backup_count,
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        handlers.append(file_handler)

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)


logger = logging.getLogger(__name__)


async def _session_cleanup_loop(session_mgr, expiry_timeout: float) -> None:
    """Periodically clean up expired device sessions."""
    interval = max(expiry_timeout / 2, 1.0)
    while True:
        try:
            await asyncio.sleep(interval)
            expired = session_mgr.cleanup_expired()
            for device_id in expired:
                edge_device_status.labels(device_id=device_id).set(0)
                logger.info(f"Session expired and cleaned: {device_id}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Neuro-Pipeline Central Server")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML file")
    parser.add_argument("--host", default=None, help="Server host")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--model-path", type=Path, default=None, help="MLX model path")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard in same process")
    parser.add_argument("--dashboard-port", type=int, default=8000, help="Dashboard port")
    args = parser.parse_args()

    cfg = AppConfig.from_yaml(args.config) if args.config else AppConfig()
    cfg.validate()
    setup_logging(cfg)

    host = args.host or cfg.central.host
    port = args.port or cfg.central.port
    model_path = Path(args.model_path or cfg.central.model_path)

    logger.info("=" * 60)
    logger.info(f"  Neuro-Pipeline Central Server v{__version__}")
    logger.info("=" * 60)
    logger.info(f"Host: {host}:{port}  TLS: {cfg.tls.enabled}")
    logger.info(f"Model: {model_path}  Mode: {cfg.central.inference_mode}")
    logger.info(f"VLM rules: {len(cfg.vlm_rules)}  Batch: {cfg.batch.max_size}x{cfg.batch.timeout_seconds}s")
    logger.info(f"Sessions: max {cfg.sessions.max_devices} devices, expiry {cfg.sessions.expiry_timeout}s")
    logger.info(f"Storage: {cfg.storage.db_path}  Cloud: {cfg.cloud_storage.enabled}")
    logger.info(f"Tracing: {cfg.tracing.enabled}  Metrics: {cfg.metrics.enabled}")

    # --- Subsystem init ---

    # Detection store (SQLite)
    db_path = Path(cfg.storage.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = DetectionStore(db_path, retention_days=cfg.storage.retention_days)

    # Device session manager
    session_mgr = DeviceSessionManager(
        max_devices=cfg.sessions.max_devices,
        expiry_timeout=cfg.sessions.expiry_timeout,
    )

    # Circuit breaker
    breaker = CircuitBreaker(
        failure_threshold=cfg.circuit_breaker.failure_threshold,
        recovery_timeout=cfg.circuit_breaker.recovery_timeout,
        half_open_max=cfg.circuit_breaker.half_open_max,
    )

    # Alert manager (always create when enabled, even without webhook — log-only alerts still fire)
    alert_mgr = None
    if cfg.alerting.enabled:
        alert_rules = [
            AlertRule(name=r.name, cooldown_seconds=r.cooldown_seconds)
            for r in cfg.alerting.rules
        ]
        alert_routes = []
        if hasattr(cfg.alerting, 'routes'):
            for route_cfg in getattr(cfg.alerting, 'routes', []):
                sev = getattr(route_cfg, 'severity', 'critical')
                url = getattr(route_cfg, 'webhook_url', '')
                alert_routes.append(AlertRoute(
                    severity=AlertSeverity(sev) if isinstance(sev, str) else sev,
                    webhook_url=url,
                ))
        alert_mgr = AlertManager(
            rules=alert_rules,
            webhook_url=cfg.alerting.webhook_url,
            routes=alert_routes if alert_routes else None,
        )

    # Cloud storage (lazy boto3)
    cloud = None
    if cfg.cloud_storage.enabled:
        cloud = CloudStorageClient(
            bucket=cfg.cloud_storage.bucket,
            prefix=cfg.cloud_storage.prefix,
            endpoint_url=cfg.cloud_storage.endpoint_url,
            region=cfg.cloud_storage.region,
        )

    # Distributed tracing (lazy OTel)
    if cfg.tracing.enabled:
        from src.observability.tracing import init_tracing
        init_tracing(cfg.tracing.service_name, cfg.tracing.endpoint)

    # Prometheus metrics endpoint
    if cfg.metrics.enabled:
        try:
            from prometheus_client import start_http_server
            start_http_server(cfg.metrics.port)
            logger.info(f"Prometheus metrics on :{cfg.metrics.port}/metrics")
        except Exception as e:
            logger.warning(f"Metrics server failed: {e}")

    # VLM trigger rules
    vlm_rules = [
        VLMTriggerRule(
            class_name=r.class_name,
            min_confidence=r.min_confidence,
            prompt_template=r.prompt_template,
        )
        for r in cfg.vlm_rules
    ]

    # Orchestrator (core logic)
    vlm_model_path = Path(cfg.central.vlm_model_path) if cfg.central.vlm_model_path else None

    # v2: Behavior analyzer
    behavior_analyzer = None
    if True:  # always available, lightweight
        from src.pipeline.behavior_analyzer import BehaviorAnalyzer
        behavior_analyzer = BehaviorAnalyzer(detection_store=store)

    # v2: Reasoning chain
    reasoning_chain = None
    if cfg.reasoning.enabled:
        from src.inference.reasoning_chain import ReasoningChain
        reasoning_chain = ReasoningChain(
            max_steps=cfg.reasoning.max_steps,
            timeout_per_step=cfg.reasoning.timeout_per_step,
        )
        logger.info(f"Reasoning chain: {cfg.reasoning.max_steps} steps, {cfg.reasoning.timeout_per_step}s/step")

    # v2: RAG retriever
    rag_retriever = None
    if cfg.rag.enabled:
        from src.inference.rag_retriever import RAGRetriever
        rag_retriever = RAGRetriever(
            detection_store=store,
            max_items=cfg.rag.max_history_items,
            time_window_hours=cfg.rag.time_window_hours,
        )
        logger.info(f"RAG retriever: {cfg.rag.max_history_items} items, {cfg.rag.time_window_hours}h window")

    # v2: Anomaly baseline
    anomaly_baseline = None
    if cfg.anomaly.enabled:
        from src.pipeline.anomaly_baseline import AnomalyBaseline
        anomaly_baseline = AnomalyBaseline(
            detection_store=store,
            baseline_window_hours=cfg.anomaly.baseline_window_hours,
            z_score_threshold=cfg.anomaly.z_score_threshold,
            min_samples=cfg.anomaly.min_samples,
        )
        logger.info(f"Anomaly baseline: z>{cfg.anomaly.z_score_threshold}, window={cfg.anomaly.baseline_window_hours}h")

    # v2: ReID engine (cross-camera re-identification)
    reid_engine = None
    if cfg.reid.enabled:
        from src.analytics.reid_engine import ReIDEngine
        reid_engine = ReIDEngine(
            similarity_threshold=cfg.reid.similarity_threshold,
            time_window_seconds=cfg.reid.time_window_seconds,
        )
        logger.info(f"ReID engine: threshold={cfg.reid.similarity_threshold}, window={cfg.reid.time_window_seconds}s")

    # v2: Time series engine
    timeseries_engine = None
    if cfg.timeseries.enabled:
        from src.analytics.timeseries_engine import TimeSeriesEngine
        timeseries_engine = TimeSeriesEngine(detection_store=store)
        logger.info(f"Time series engine: interval={cfg.timeseries.aggregation_interval}s")

    # v2: Auto annotator
    auto_annotator = None
    if cfg.auto_annotator.enabled:
        from src.analytics.auto_annotator import AutoAnnotator
        auto_annotator = AutoAnnotator(
            detection_store=store,
            min_confidence=cfg.auto_annotator.min_confidence,
        )
        logger.info(f"Auto annotator: min_confidence={cfg.auto_annotator.min_confidence}")

    # v2: Report generator
    report_generator = None
    if cfg.reporting.enabled:
        from src.analytics.report_generator import ReportGenerator
        report_generator = ReportGenerator(
            detection_store=store,
            cloud_storage=cloud,
        )
        logger.info(f"Report generator: schedule={cfg.reporting.schedule_hours}h")

    orchestrator = CentralOrchestrator(
        model_path,
        vlm_rules=vlm_rules,
        detection_store=store,
        inference_mode=cfg.central.inference_mode,
        vlm_model_path=vlm_model_path,
        circuit_breaker=breaker,
        alert_manager=alert_mgr,
        cloud_storage=cloud,
        batch_config=cfg.batch,
        behavior_analyzer=behavior_analyzer,
        reasoning_chain=reasoning_chain,
        rag_retriever=rag_retriever,
        anomaly_baseline=anomaly_baseline,
    )
    await orchestrator.initialize()

    # Rate limiter
    rate_limiter = None
    if cfg.rate_limiting.enabled:
        from src.communication.rate_limiter import TokenBucketRateLimiter
        rate_limiter = TokenBucketRateLimiter(
            max_per_sec=cfg.rate_limiting.max_rps,
            burst=cfg.rate_limiting.burst,
        )
        logger.info(f"Rate limiting: {cfg.rate_limiting.max_rps} rps, burst {cfg.rate_limiting.burst}")

    # Model registry (v2)
    model_registry = None
    if cfg.model_management.enabled:
        from src.model_management.model_registry import ModelRegistry
        model_registry = ModelRegistry(
            max_models_per_device=cfg.model_management.max_models_per_device,
        )
        logger.info(f"Model management: max {cfg.model_management.max_models_per_device} models/device")

    # A/B test manager (v2)
    ab_test_manager = None
    if cfg.ab_test.enabled:
        from src.model_management.ab_test_manager import ABTestManager
        ab_test_manager = ABTestManager(
            traffic_split=cfg.ab_test.traffic_split,
            min_samples=cfg.ab_test.min_samples,
            metric=cfg.ab_test.metric,
        )
        logger.info(f"A/B testing: split={cfg.ab_test.traffic_split}, metric={cfg.ab_test.metric}")

    # gRPC server (with mTLS + session manager + rate limiter + model registry)
    server = NeuroPipelineServer(
        host, port, orchestrator,
        max_message_size_mb=cfg.central.max_message_size_mb,
        tls_config=cfg.tls if cfg.tls.enabled else None,
        session_manager=session_mgr,
        rate_limiter=rate_limiter,
        model_registry=model_registry,
        detection_store=store,
        ab_test_manager=ab_test_manager,
    )
    await server.start()

    # Session cleanup background task
    cleanup_task = asyncio.create_task(
        _session_cleanup_loop(session_mgr, cfg.sessions.expiry_timeout)
    )

    # --- Hot reload ---
    config_path = str(args.config) if args.config else None
    config_watcher = None
    if config_path:
        async def _on_config_change(path, change):
            try:
                new_cfg = AppConfig.from_yaml(Path(config_path))
                new_cfg.validate()
                # Logging level
                new_level = getattr(logging, new_cfg.logging.level.upper(), None)
                if new_level and new_level != logging.getLogger().level:
                    logging.getLogger().setLevel(new_level)
                    logger.info(f"Log level changed to {new_cfg.logging.level}")
                # VLM rules
                new_vlm_rules = [
                    VLMTriggerRule(
                        class_name=r.class_name,
                        min_confidence=r.min_confidence,
                        prompt_template=r.prompt_template,
                    )
                    for r in new_cfg.vlm_rules
                ]
                orchestrator.vlm_rules = new_vlm_rules
                # Rate limiter
                if rate_limiter and new_cfg.rate_limiting.enabled:
                    rate_limiter.update_limits(
                        new_cfg.rate_limiting.max_rps,
                        new_cfg.rate_limiting.burst,
                    )
                # Alert manager
                if alert_mgr and new_cfg.alerting.enabled:
                    from src.observability.alerting import AlertRule as _AR, AlertSeverity as _AS, AlertRoute as _ARt
                    new_rules = [_AR(name=r.name, cooldown_seconds=r.cooldown_seconds) for r in new_cfg.alerting.rules]
                    new_routes = [_ARt(severity=_AS(rt.severity), webhook_url=rt.webhook_url) for rt in new_cfg.alerting.routes]
                    alert_mgr.update_rules(new_rules, new_routes)
                logger.info("Config hot-reloaded successfully")
            except Exception as e:
                logger.error(f"Config reload failed (keeping current): {e}")

        config_watcher = get_config_watcher()
        config_watcher.watch(config_path, async_callback=_on_config_change)
        await config_watcher.start()
        logger.info(f"Config watcher started for {config_path}")

    # Embedded dashboard (same process, shares subsystem instances)
    dashboard_server = None
    if args.dashboard:
        from dashboard.app import app as dashboard_app, inject_from_central
        inject_from_central(
            detection_store=store,
            session_manager=session_mgr,
            orchestrator=orchestrator,
            health_checker=None,
            ab_test_manager=ab_test_manager,
            model_registry=model_registry,
            reid_engine=reid_engine,
            timeseries_engine=timeseries_engine,
            auto_annotator=auto_annotator,
            report_generator=report_generator,
            behavior_analyzer=behavior_analyzer,
            anomaly_baseline=anomaly_baseline,
            reasoning_chain=reasoning_chain,
            rag_retriever=rag_retriever,
        )
        import uvicorn
        dashboard_config = uvicorn.Config(
            dashboard_app, host="0.0.0.0", port=args.dashboard_port, log_level="info"
        )
        dashboard_server = uvicorn.Server(dashboard_config)
        asyncio.create_task(dashboard_server.serve())
        logger.info(f"Dashboard started on :{args.dashboard_port}")

    # Graceful shutdown
    stop_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Server running. Press Ctrl+C to stop.")
    await stop_event.wait()

    logger.info("Shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    if config_watcher:
        await config_watcher.stop()
    if dashboard_server:
        dashboard_server.should_exit = True
    try:
        await asyncio.wait_for(_shutdown_sequence(server, orchestrator, store), timeout=60)
    except asyncio.TimeoutError:
        logger.error("Global shutdown timeout (60s), forcing exit")
    logger.info("Shutdown complete")


async def _shutdown_sequence(server, orchestrator, store):
    await server.stop()
    await orchestrator.shutdown()
    store.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
