"""End-to-end integration test: gRPC server + simulated edge client."""

import asyncio
import pytest
import pytest_asyncio
import grpc

from src.generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc
from src.communication.grpc_server import NeuroPipelineServer
from src.pipeline.central_orchestrator import CentralOrchestrator
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


@pytest_asyncio.fixture
async def grpc_server_and_channel():
    """Start a real gRPC server and return (server, channel)."""
    orchestrator = CentralOrchestrator(Path("models/test"))
    # Patch inference engine to avoid loading real model
    orchestrator.inference_engine = MagicMock()
    orchestrator.inference_engine.load_model = AsyncMock()
    orchestrator.inference_engine.unload_model = AsyncMock()
    orchestrator.inference_engine.analyze_image = AsyncMock(return_value="test result")

    server = NeuroPipelineServer("localhost", 0, orchestrator)
    await server.start()

    # Get the actual port
    port = server.server.add_insecure_port("localhost:0")
    # Re-start on that port
    await server.stop(grace=0.1)

    server = NeuroPipelineServer("localhost", 50099, orchestrator)
    await server.start()

    channel = grpc.aio.insecure_channel("localhost:50099")
    yield server, channel, orchestrator

    await channel.close()
    await server.stop(grace=0.1)


@pytest.mark.asyncio
async def test_e2e_health_check(grpc_server_and_channel):
    """Health check returns SERVING."""
    server, channel, _ = grpc_server_and_channel
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(channel)

    response = await stub.HealthCheck(
        neuro_pipeline_pb2.HealthCheckRequest(client_id="test")
    )
    assert response.status == neuro_pipeline_pb2.HealthCheckResponse.SERVING
    assert response.version == "2.3.1"


@pytest.mark.asyncio
async def test_e2e_stream_detection(grpc_server_and_channel):
    """Stream detection results and get response."""
    server, channel, orchestrator = grpc_server_and_channel
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(channel)

    async def generate_detections():
        for i in range(3):
            result = neuro_pipeline_pb2.DetectionResult()
            result.frame_id = i
            result.device_id = "edge-test"
            result.trace_id = f"test-{i}"
            yield result

    response = await stub.StreamDetectionResults(generate_detections())
    assert response.success is True
    assert response.frames_received == 3


@pytest.mark.asyncio
async def test_e2e_control_command(grpc_server_and_channel):
    """Send control command and verify it's queued."""
    server, channel, orchestrator = grpc_server_and_channel
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(channel)

    cmd = neuro_pipeline_pb2.ControlCommand()
    cmd.type = neuro_pipeline_pb2.ControlCommand.SET_FPS
    cmd.command_id = 99
    cmd.parameters["fps"] = "15"

    response = await stub.SendControlCommand(cmd)
    assert response.success is True
    assert response.command_id == 99

    # Verify command was queued in orchestrator
    queued = await asyncio.wait_for(orchestrator.get_pending_command(), timeout=1.0)
    assert queued.command_id == 99
