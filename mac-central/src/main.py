#!/usr/bin/env python3
"""Central server main entry point — wires all subsystems from config."""
import argparse
import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from communication.grpc_server import NeuroPipelineServer
from application_logic.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from communication.device_session import DeviceSessionManager
from config import AppConfig
from observability.circuit_breaker import CircuitBreaker
from observability.alerting import AlertManager, AlertRule, AlertSeverity, AlertRoute
from observability.metrics import edge_device_status
from storage.detection_store import DetectionStore
from storage.cloud_storage import CloudStorageClient


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
    args = parser.parse_args()

    cfg = AppConfig.from_yaml(args.config) if args.config else AppConfig()
    cfg.validate()
    setup_logging(cfg)

    host = args.host or cfg.central.host
    port = args.port or cfg.central.port
    model_path = Path(args.model_path or cfg.central.model_path)

    logger.info("=" * 60)
    logger.info("  Neuro-Pipeline Central Server v1.3.0")
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
        from observability.tracing import init_tracing
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
    )
    await orchestrator.initialize()

    # Rate limiter
    rate_limiter = None
    if cfg.rate_limiting.enabled:
        from communication.rate_limiter import TokenBucketRateLimiter
        rate_limiter = TokenBucketRateLimiter(
            max_per_sec=cfg.rate_limiting.max_rps,
            burst=cfg.rate_limiting.burst,
        )
        logger.info(f"Rate limiting: {cfg.rate_limiting.max_rps} rps, burst {cfg.rate_limiting.burst}")

    # gRPC server (with mTLS + session manager + rate limiter)
    server = NeuroPipelineServer(
        host, port, orchestrator,
        max_message_size_mb=cfg.central.max_message_size_mb,
        tls_config=cfg.tls if cfg.tls.enabled else None,
        session_manager=session_mgr,
        rate_limiter=rate_limiter,
    )
    await server.start()

    # Session cleanup background task
    cleanup_task = asyncio.create_task(
        _session_cleanup_loop(session_mgr, cfg.sessions.expiry_timeout)
    )

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
