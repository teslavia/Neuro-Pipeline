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
from src.observability.metrics import grpc_requests_total, grpc_latency, edge_connections, control_commands_total, grpc_validation_errors


class NeuroPipelineServicer(neuro_pipeline_pb2_grpc.NeuroPipelineServiceServicer):
    """gRPC service implementation for Neuro-Pipeline."""

    def __init__(self, orchestrator, session_manager=None, rate_limiter=None,
                 model_registry=None, detection_store=None, ab_test_manager=None) -> None:
        self.orchestrator = orchestrator
        self.session_manager = session_manager
        self._rate_limiter = rate_limiter
        self._model_registry = model_registry
        self._detection_store = detection_store
        self._ab_test_manager = ab_test_manager
        logger.info("NeuroPipelineServicer initialized")

    @staticmethod
    def _validate_detection(result) -> str | None:
        """Validate a DetectionResult message. Returns error string or None."""
        if not result.device_id:
            return "device_id must not be empty"
        for box in result.boxes:
            if not (0.0 <= box.confidence <= 1.0):
                return f"confidence out of range [0,1]: {box.confidence}"
            for coord_name in ("x_min", "y_min", "x_max", "y_max"):
                val = getattr(box, coord_name, 0.0)
                if not (0.0 <= val <= 1.0):
                    return f"{coord_name} out of range [0,1]: {val}"
        return None

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
        device_id = ""

        try:
            async for result in request_iterator:
                t0 = time.perf_counter()
                # Extract device_id from first message and register session
                if not device_id and result.device_id:
                    device_id = result.device_id
                    if self.session_manager:
                        self.session_manager.register(device_id)

                # Rate limiting
                if self._rate_limiter and not self._rate_limiter.allow(device_id):
                    grpc_requests_total.labels(method="StreamDetectionResults", status="rate_limited").inc()
                    await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Rate limit exceeded")
                    return

                # Input validation
                validation_err = self._validate_detection(result)
                if validation_err:
                    grpc_validation_errors.labels(reason=validation_err[:50]).inc()
                    logger.warning(f"Validation failed: {validation_err}")
                    # Skip invalid message but continue stream
                    continue

                logger.debug(
                    f"Received detection result: frame_id={result.frame_id}, "
                    f"boxes={len(result.boxes)}, device_id={device_id}"
                )
                await self.orchestrator.process_detection(result)
                frames_received += 1
                if self.session_manager and device_id:
                    self.session_manager.heartbeat(device_id)
                    self.session_manager.increment_frames(device_id)
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
            if self.session_manager and device_id:
                self.session_manager.unregister(device_id)

        return neuro_pipeline_pb2.StreamResponse(
            success=True,
            message=f"Processed {frames_received} frames",
            frames_received=frames_received,
        )

    async def SendControlCommand(self, request, context: grpc.aio.ServicerContext):
        """Send control command to edge device via command queue."""
        import time as _time
        # Audit log
        audit_entry = {
            "action": "control_command",
            "command_type": str(request.type),
            "command_id": request.command_id,
            "device_id": getattr(request, "device_id", ""),
            "timestamp": _time.time(),
        }
        logger.info(f"AUDIT: {audit_entry}")
        control_commands_total.labels(command_type=str(request.type)).inc()

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
            status=status, version="2.1.0"
        )

    async def RegisterDevice(self, request, context: grpc.aio.ServicerContext):
        """Register an edge device."""
        logger.info(f"Device registration: {request.device_id} ({request.device_name})")
        grpc_requests_total.labels(method="RegisterDevice", status="ok").inc()
        if self.session_manager:
            ok = self.session_manager.register(
                device_id=request.device_id,
                device_name=request.device_name,
                firmware_version=request.firmware_version,
                capabilities=list(request.capabilities),
            )
            if not ok:
                return neuro_pipeline_pb2.DeviceRegistrationResponse(
                    success=False,
                    message="Max devices reached",
                    assigned_id=request.device_id,
                )
            # A/B test group assignment
            if self._ab_test_manager:
                group = self._ab_test_manager.assign_group(request.device_id)
                session = self.session_manager.get_session(request.device_id)
                if session:
                    session.ab_test_group = group.value
                    session.model_version = self._ab_test_manager.get_variant(request.device_id)
        return neuro_pipeline_pb2.DeviceRegistrationResponse(
            success=True,
            message="Registered",
            assigned_id=request.device_id,
        )

    async def ManageModel(self, request, context: grpc.aio.ServicerContext):
        """v2: Model lifecycle management."""
        grpc_requests_total.labels(method="ManageModel", status="ok").inc()
        action = request.action
        model = request.model

        if not self._model_registry:
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=False, message="Model management not enabled"
            )

        # DEPLOY
        if action == neuro_pipeline_pb2.ModelManagementRequest.DEPLOY:
            ok = self._model_registry.deploy(
                model_id=model.model_id,
                model_path=model.model_path,
                model_type=model.model_type,
                version=model.version,
                target_device_id=request.target_device_id,
                npu_core=request.npu_core,
                metadata=dict(model.metadata),
            )
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=ok, message="Deployed" if ok else "Deploy failed"
            )

        # UNDEPLOY
        if action == neuro_pipeline_pb2.ModelManagementRequest.UNDEPLOY:
            ok = self._model_registry.undeploy(model.model_id)
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=ok, message="Undeployed" if ok else "Undeploy failed"
            )

        # LIST
        if action == neuro_pipeline_pb2.ModelManagementRequest.LIST:
            records = self._model_registry.list_models(device_id=request.target_device_id)
            model_infos = [
                neuro_pipeline_pb2.ModelInfo(
                    model_id=r.model_id, model_path=r.model_path,
                    model_type=r.model_type, version=r.version,
                    metadata=r.metadata,
                )
                for r in records
            ]
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=True, message=f"{len(model_infos)} models", models=model_infos
            )

        # ROLLBACK
        if action == neuro_pipeline_pb2.ModelManagementRequest.ROLLBACK:
            ok = self._model_registry.rollback(model.model_id)
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=ok, message="Rolled back" if ok else "Rollback failed"
            )

        # STATUS
        if action == neuro_pipeline_pb2.ModelManagementRequest.STATUS:
            record = self._model_registry.get_model(model.model_id)
            if not record:
                return neuro_pipeline_pb2.ModelManagementResponse(
                    success=False, message="Model not found"
                )
            info = neuro_pipeline_pb2.ModelInfo(
                model_id=record.model_id, model_path=record.model_path,
                model_type=record.model_type, version=record.version,
                metadata={**record.metadata, "status": record.status.value},
            )
            return neuro_pipeline_pb2.ModelManagementResponse(
                success=True, message=record.status.value, models=[info]
            )

        return neuro_pipeline_pb2.ModelManagementResponse(
            success=False, message=f"Unknown action: {action}"
        )

    async def QueryTimeSeries(self, request, context: grpc.aio.ServicerContext):
        """v2: Query time-series metrics."""
        grpc_requests_total.labels(method="QueryTimeSeries", status="ok").inc()

        if not self._detection_store or not hasattr(self._detection_store, 'query_timeseries'):
            return neuro_pipeline_pb2.TimeSeriesResponse(
                success=False, message="Time series not available"
            )

        rows = self._detection_store.query_timeseries(
            metric_name=request.metric_name,
            device_id=request.device_id,
            start_time=request.start_time,
            end_time=request.end_time if request.end_time > 0 else 0,
            aggregation=request.aggregation or "avg",
            bucket_seconds=request.bucket_seconds or 0,
        )
        points = [
            neuro_pipeline_pb2.TimeSeriesPoint(
                timestamp=r["timestamp"], value=r["value"],
                labels=r.get("labels", {}),
            )
            for r in rows
        ]
        return neuro_pipeline_pb2.TimeSeriesResponse(
            success=True, message=f"{len(points)} points", points=points
        )


class NeuroPipelineServer:
    """Async gRPC server wrapper with optional mTLS."""

    def __init__(self, host: str, port: int, orchestrator,
                 max_message_size_mb: int = 16, tls_config=None,
                 session_manager=None, rate_limiter=None,
                 model_registry=None, detection_store=None,
                 ab_test_manager=None) -> None:
        self.host = host
        self.port = port
        self.orchestrator = orchestrator
        self.max_message_size_mb = max_message_size_mb
        self.tls_config = tls_config
        self.session_manager = session_manager
        self.rate_limiter = rate_limiter
        self.model_registry = model_registry
        self.detection_store = detection_store
        self.ab_test_manager = ab_test_manager
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
            NeuroPipelineServicer(
                self.orchestrator,
                session_manager=self.session_manager,
                rate_limiter=self.rate_limiter,
                model_registry=self.model_registry,
                detection_store=self.detection_store,
                ab_test_manager=self.ab_test_manager,
            ),
            self.server,
        )

        # Enable gRPC reflection for grpcurl / debugging
        try:
            from grpc_reflection.v1alpha import reflection
            service_names = (
                neuro_pipeline_pb2.DESCRIPTOR.services_by_name['NeuroPipelineService'].full_name,
                reflection.SERVICE_NAME,
            )
            reflection.enable_server_reflection(service_names, self.server)
        except ImportError:
            logger.debug("grpc-reflection not installed, reflection disabled")

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
