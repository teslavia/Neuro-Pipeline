#!/usr/bin/env python3
"""
Neuro-Pipeline Central Server (Mac Mini)

Main entry point for the gRPC server that receives edge detection results
and performs MLX-based VLM inference.
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Neuro-Pipeline Central Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="gRPC server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=50051,
        help="gRPC server port (default: 50051)",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path("models/"),
        help="Path to MLX model directory",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


async def main() -> None:
    """Main async entry point."""
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Neuro-Pipeline Central Server v1.1.0")
    logger.info(f"gRPC server will listen on {args.host}:{args.port}")

    # TODO: Import and initialize when generated protobuf code is available
    # from src.communication.grpc_server import NeuroPipelineServer
    # from src.application_logic.central_orchestrator import CentralOrchestrator

    # orchestrator = CentralOrchestrator(model_path=args.model_path)
    # await orchestrator.initialize()

    # server = NeuroPipelineServer(
    #     host=args.host,
    #     port=args.port,
    #     orchestrator=orchestrator,
    # )

    # Graceful shutdown handler
    stop_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # await server.start()
    logger.info("Server started successfully (stub). Press Ctrl+C to stop.")

    # Wait for shutdown signal
    await stop_event.wait()

    # await server.stop()
    # await orchestrator.shutdown()
    logger.info("Server stopped gracefully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
