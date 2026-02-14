"""
gRPC server implementation for receiving edge detection results.
"""

import asyncio
import logging
from typing import AsyncIterator

import grpc

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

from src.generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc
from src.observability.metrics import grpc_requests_total, grpc_latency, edge_connections


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
        import time
        frames_received = 0
        edge_connections.inc()

        try:
            async for result in request_iterator:
                t0 = time.perf_counter()
                logger.debug(
                    f"Received detection result: frame_id={result.frame_id}, "
                    f"boxes={len(result.boxes)}"
                )
                await self.orchestrator.process_detection(result)
                frames_received += 1
                elapsed = time.perf_counter() - t0
                grpc_latency.labels(method="StreamDetectionResults").observe(elapsed)
                grpc_requests_total.labels(method="StreamDetectionResults", status="ok").inc()
                logger.info(f"[Perf] Processing latency: {elapsed*1000:.1f}ms")

        except Exception as e:
            grpc_requests_total.labels(method="StreamDetectionResults", status="error").inc()
            logger.error(f"Error during streaming: {e}")
            return neuro_pipeline_pb2.StreamResponse(
                success=False, message=str(e), frames_received=frames_received
            )
        finally:
            edge_connections.dec()

        return neuro_pipeline_pb2.StreamResponse(
            success=True,
            message=f"Processed {frames_received} frames",
            frames_received=frames_received,
        )

    async def SendControlCommand(self, request, context: grpc.aio.ServicerContext):
        """Send control command to edge device via command queue."""
        logger.info(f"Received control command: type={request.type}, id={request.command_id}")
        await self.orchestrator.send_command(request)
        return neuro_pipeline_pb2.CommandResponse(
            success=True,
            message="Command queued",
            command_id=request.command_id,
        )

    async def BidirectionalEventStream(
        self,
        request_iterator: AsyncIterator,
        context: grpc.aio.ServicerContext,
    ):
        """Bidirectional event streaming with command forwarding."""

        async def read_events():
            try:
                async for event in request_iterator:
                    logger.debug(f"Received edge event: type={event.type}")
                    await self.orchestrator.handle_edge_event(event)
            except asyncio.CancelledError:
                pass

        reader_task = asyncio.create_task(read_events())

        try:
            while not context.cancelled():
                try:
                    cmd = await asyncio.wait_for(
                        self.orchestrator.get_pending_command(), timeout=1.0
                    )
                    yield neuro_pipeline_pb2.CentralEvent(
                        type=neuro_pipeline_pb2.CentralEvent.CONTROL_COMMAND,
                        timestamp_us=0,
                        payload=f"command_id={cmd.command_id}",
                        command=cmd,
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass

    async def HealthCheck(self, request, context: grpc.aio.ServicerContext):
        """Health check endpoint with readiness awareness."""
        logger.debug(f"Health check from client: {request.client_id}")
        grpc_requests_total.labels(method="HealthCheck", status="ok").inc()
        ready = getattr(self.orchestrator, "is_ready", lambda: True)()
        status = (
            neuro_pipeline_pb2.HealthCheckResponse.SERVING
            if ready
            else neuro_pipeline_pb2.HealthCheckResponse.NOT_SERVING
        )
        return neuro_pipeline_pb2.HealthCheckResponse(
            status=status, version="1.0.0"
        )


class NeuroPipelineServer:
    """Async gRPC server wrapper with optional mTLS."""

    def __init__(self, host: str, port: int, orchestrator,
                 max_message_size_mb: int = 16, tls_config=None) -> None:
        self.host = host
        self.port = port
        self.orchestrator = orchestrator
        self.max_message_size_mb = max_message_size_mb
        self.tls_config = tls_config
        self.server = None

    async def start(self) -> None:
        """Start gRPC server with production-grade options."""
        max_bytes = self.max_message_size_mb * 1024 * 1024
        options = [
            ("grpc.max_receive_message_length", max_bytes),
            ("grpc.max_send_message_length", max_bytes),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", 1),
            ("grpc.http2.max_pings_without_data", 0),
        ]
        self.server = grpc.aio.server(options=options, compression=grpc.Compression.Gzip)

        neuro_pipeline_pb2_grpc.add_NeuroPipelineServiceServicer_to_server(
            NeuroPipelineServicer(self.orchestrator), self.server
        )

        listen_addr = f"{self.host}:{self.port}"

        if self.tls_config and self.tls_config.enabled:
            with open(self.tls_config.server_key, 'rb') as f:
                key = f.read()
            with open(self.tls_config.server_cert, 'rb') as f:
                cert = f.read()
            with open(self.tls_config.ca_cert, 'rb') as f:
                ca = f.read()
            creds = grpc.ssl_server_credentials(
                [(key, cert)], ca, require_client_auth=True
            )
            self.server.add_secure_port(listen_addr, creds)
            logger.info(f"gRPC server listening on {listen_addr} (mTLS)")
        else:
            self.server.add_insecure_port(listen_addr)
            logger.info(f"gRPC server listening on {listen_addr} (insecure)")

        await self.server.start()

    async def stop(self, grace: float = 5.0) -> None:
        """Stop gRPC server gracefully."""
        if self.server:
            logger.info("Stopping gRPC server...")
            await self.server.stop(grace)
            logger.info("gRPC server stopped")
