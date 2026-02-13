#!/usr/bin/env python3
"""Central server main entry point."""
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from communication.grpc_server import NeuroPipelineServer
from application_logic.central_orchestrator import CentralOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Neuro-Pipeline Central Server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=50051, help="Server port")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path("models/Llama-3.2-3B-Instruct"),
        help="MLX model path",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  Neuro-Pipeline Central Server v0.3.0")
    logger.info("=" * 60)
    logger.info(f"Host: {args.host}:{args.port}")
    logger.info(f"Model: {args.model_path}")
    logger.info("")

    orchestrator = CentralOrchestrator(args.model_path)
    await orchestrator.initialize()

    server = NeuroPipelineServer(args.host, args.port, orchestrator)
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
