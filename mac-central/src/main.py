#!/usr/bin/env python3
"""Central server main entry point."""
import argparse
import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from communication.grpc_server import NeuroPipelineServer
from application_logic.central_orchestrator import CentralOrchestrator, VLMTriggerRule
from config import AppConfig


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


async def main():
    parser = argparse.ArgumentParser(description="Neuro-Pipeline Central Server")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML file")
    parser.add_argument("--host", default=None, help="Server host")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="MLX model path",
    )
    args = parser.parse_args()

    # Load config: file defaults → CLI overrides
    cfg = AppConfig.from_yaml(args.config) if args.config else AppConfig()

    # Setup logging (must be before any log calls)
    setup_logging(cfg)

    host = args.host or cfg.central.host
    port = args.port or cfg.central.port
    model_path = Path(args.model_path or cfg.central.model_path)

    logger.info("=" * 60)
    logger.info("  Neuro-Pipeline Central Server v0.5.0")
    logger.info("=" * 60)
    logger.info(f"Host: {host}:{port}")
    logger.info(f"Model: {model_path}")
    logger.info(f"VLM rules: {len(cfg.vlm_rules)} loaded")
    logger.info("")

    vlm_rules = [
        VLMTriggerRule(
            class_name=r.class_name,
            min_confidence=r.min_confidence,
            prompt_template=r.prompt_template,
        )
        for r in cfg.vlm_rules
    ]
    orchestrator = CentralOrchestrator(model_path, vlm_rules=vlm_rules)
    await orchestrator.initialize()

    server = NeuroPipelineServer(host, port, orchestrator)
    await server.start()

    stop_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Server running. Press Ctrl+C to stop.")
    await stop_event.wait()

    logger.info("Shutting down...")
    await server.stop()
    await orchestrator.shutdown()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
