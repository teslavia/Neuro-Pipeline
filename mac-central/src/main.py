#!/usr/bin/env python3
"""Central server main entry point — wires all subsystems via ServiceContainer."""
import argparse
import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import AppConfig
from src.core import __version__
from src.core.container import ServiceContainer
from src.core.hot_reload import get_config_watcher
from src.observability.metrics import edge_device_status
from src.pipeline.central_orchestrator import VLMTriggerRule


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

    # CLI overrides
    if args.host:
        cfg.central.host = args.host
    if args.port:
        cfg.central.port = args.port
    if args.model_path:
        cfg.central.model_path = str(args.model_path)

    setup_logging(cfg)

    logger.info("=" * 60)
    logger.info(f"  Neuro-Pipeline Central Server v{__version__}")
    logger.info("=" * 60)
    logger.info(f"Host: {cfg.central.host}:{cfg.central.port}  TLS: {cfg.tls.enabled}")
    logger.info(f"Model: {cfg.central.model_path}  Mode: {cfg.central.inference_mode}")
    logger.info(f"VLM rules: {len(cfg.vlm_rules)}  Batch: {cfg.batch.max_size}x{cfg.batch.timeout_seconds}s")
    logger.info(f"Sessions: max {cfg.sessions.max_devices} devices, expiry {cfg.sessions.expiry_timeout}s")
    logger.info(f"Storage: {cfg.storage.db_path}  Cloud: {cfg.cloud_storage.enabled}")
    logger.info(f"Tracing: {cfg.tracing.enabled}  Metrics: {cfg.metrics.enabled}")

    # --- Build services via container ---
    container = ServiceContainer(cfg)

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

    orchestrator = container.get("orchestrator")
    await orchestrator.initialize()

    server = container.get("grpc_server")
    await server.start()

    session_mgr = container.get("session_manager")
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
                new_level = getattr(logging, new_cfg.logging.level.upper(), None)
                if new_level and new_level != logging.getLogger().level:
                    logging.getLogger().setLevel(new_level)
                    logger.info(f"Log level changed to {new_cfg.logging.level}")
                new_vlm_rules = [
                    VLMTriggerRule(
                        class_name=r.class_name,
                        min_confidence=r.min_confidence,
                        prompt_template=r.prompt_template,
                    )
                    for r in new_cfg.vlm_rules
                ]
                orchestrator.vlm_rules = new_vlm_rules
                rate_limiter = container.get("rate_limiter")
                if rate_limiter and new_cfg.rate_limiting.enabled:
                    rate_limiter.update_limits(
                        new_cfg.rate_limiting.max_rps,
                        new_cfg.rate_limiting.burst,
                    )
                alert_mgr = container.get("alert_manager")
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

    # Embedded dashboard
    dashboard_server = None
    if args.dashboard:
        from dashboard.app import app as dashboard_app, inject_from_central
        inject_from_central(
            detection_store=container.get("store"),
            session_manager=session_mgr,
            orchestrator=orchestrator,
            health_checker=None,
            ab_test_manager=container.get("ab_test_manager"),
            model_registry=container.get("model_registry"),
            reid_engine=container.get("reid_engine"),
            timeseries_engine=container.get("timeseries_engine"),
            auto_annotator=container.get("auto_annotator"),
            report_generator=container.get("report_generator"),
            behavior_analyzer=container.get("behavior_analyzer"),
            anomaly_baseline=container.get("anomaly_baseline"),
            reasoning_chain=container.get("reasoning_chain"),
            rag_retriever=container.get("rag_retriever"),
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
        await asyncio.wait_for(
            _shutdown_sequence(server, orchestrator, container.get("store")),
            timeout=60,
        )
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
