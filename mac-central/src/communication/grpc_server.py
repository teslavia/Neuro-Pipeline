"""
gRPC server implementation for receiving edge detection results.
"""

import asyncio
import logging
from typing import AsyncIterator

import grpc
from src.generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc

logger = logging.getLogger(__name__)


class NeuroPipelineServicer(neuro_pipeline_pb2_grpc.NeuroPipelineServiceServicer):
    """gRPC service implementation for Neuro-Pipeline."""

    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator
        logger.info("NeuroPipelineServicer initialized")

    async def StreamDetectionResults(
        self,
        request_iterator: AsyncIterator,
        context: grpc.aio.ServicerContext,
    ):
        """
        Receive stream of detection results from edge device.

        Args:
            request_iterator: Async iterator of DetectionResult messages.
            context: gRPC context.

        Returns:
            StreamResponse with processing summary.
        """
        frames_received = 0

        try:
            async for result in request_iterator:
                logger.debug(
                    f"Received detection result: frame_id={result.frame_id}, "
                    f"boxes={len(result.boxes)}"
                )
                await self.orchestrator.process_detection(result)
                frames_received += 1

        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            return neuro_pipeline_pb2.StreamResponse(
                success=False, message=str(e), frames_received=frames_received
            )

        return neuro_pipeline_pb2.StreamResponse(
            success=True,
            message=f"Processed {frames_received} frames",
            frames_received=frames_received,
        )

    async def SendControlCommand(self, request, context: grpc.aio.ServicerContext):
        """Send control command to edge device."""
        logger.info(f"Received control command: type={request.type}")
        return neuro_pipeline_pb2.CommandResponse(
            success=True,
            message="Command received",
            command_id=request.command_id
        )

    async def BidirectionalEventStream(
        self,
        request_iterator: AsyncIterator,
        context: grpc.aio.ServicerContext,
    ):
        """Bidirectional event streaming."""
        async for event in request_iterator:
            logger.debug(f"Received edge event: type={event.type}")
            yield neuro_pipeline_pb2.CentralEvent(
                type=neuro_pipeline_pb2.CentralEvent.COMMAND_ACK,
                timestamp_us=event.timestamp_us,
                payload="Event acknowledged"
            )

    async def HealthCheck(self, request, context: grpc.aio.ServicerContext):
        """Health check endpoint."""
        logger.debug(f"Health check from client: {request.client_id}")
        return neuro_pipeline_pb2.HealthCheckResponse(
            status=neuro_pipeline_pb2.HealthCheckResponse.SERVING,
            version="0.3.0"
        )


class NeuroPipelineServer:
    """Async gRPC server wrapper."""

    def __init__(self, host: str, port: int, orchestrator) -> None:
        self.host = host
        self.port = port
        self.orchestrator = orchestrator
        self.server = None

    async def start(self) -> None:
        """Start gRPC server."""
        self.server = grpc.aio.server()

        neuro_pipeline_pb2_grpc.add_NeuroPipelineServiceServicer_to_server(
            NeuroPipelineServicer(self.orchestrator), self.server
        )

        listen_addr = f"{self.host}:{self.port}"
        self.server.add_insecure_port(listen_addr)

        await self.server.start()
        logger.info(f"gRPC server listening on {listen_addr}")

    async def stop(self, grace: float = 5.0) -> None:
        """Stop gRPC server gracefully."""
        if self.server:
            logger.info("Stopping gRPC server...")
            await self.server.stop(grace)
            logger.info("gRPC server stopped")
