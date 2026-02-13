"""Unit tests for gRPC server."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.communication.grpc_server import NeuroPipelineServicer, NeuroPipelineServer
from src.generated import neuro_pipeline_pb2


@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    orchestrator.process_detection = AsyncMock()
    return orchestrator


@pytest.fixture
def servicer(mock_orchestrator):
    return NeuroPipelineServicer(mock_orchestrator)


@pytest.mark.asyncio
async def test_stream_detection_results_success(servicer, mock_orchestrator):
    """Test successful detection result streaming."""
    async def mock_iterator():
        for i in range(3):
            result = neuro_pipeline_pb2.DetectionResult()
            result.frame_id = i
            yield result

    response = await servicer.StreamDetectionResults(mock_iterator(), None)

    assert response.success is True
    assert response.frames_received == 3
    assert mock_orchestrator.process_detection.call_count == 3


@pytest.mark.asyncio
async def test_stream_detection_results_error(servicer, mock_orchestrator):
    """Test detection streaming with processing error."""
    mock_orchestrator.process_detection.side_effect = Exception("Processing failed")

    async def mock_iterator():
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = 1
        yield result

    response = await servicer.StreamDetectionResults(mock_iterator(), None)

    assert response.success is False
    assert "Processing failed" in response.message


@pytest.mark.asyncio
async def test_health_check(servicer):
    """Test health check endpoint."""
    request = neuro_pipeline_pb2.HealthCheckRequest()
    request.client_id = "test_client"

    response = await servicer.HealthCheck(request, None)

    assert response.status == neuro_pipeline_pb2.HealthCheckResponse.SERVING
    assert response.version == "0.3.0"


@pytest.mark.asyncio
async def test_send_control_command(servicer):
    """Test control command handling."""
    request = neuro_pipeline_pb2.ControlCommand()
    request.type = neuro_pipeline_pb2.ControlCommand.SET_FPS
    request.command_id = 123

    response = await servicer.SendControlCommand(request, None)

    assert response.success is True
    assert response.command_id == 123


@pytest.mark.asyncio
async def test_bidirectional_event_stream(servicer):
    """Test bidirectional event streaming."""
    async def mock_iterator():
        event = neuro_pipeline_pb2.EdgeEvent()
        event.type = neuro_pipeline_pb2.EdgeEvent.DETECTION_ALERT
        event.timestamp_us = 1000
        yield event

    responses = []
    async for response in servicer.BidirectionalEventStream(mock_iterator(), None):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].type == neuro_pipeline_pb2.CentralEvent.COMMAND_ACK


@pytest.mark.asyncio
async def test_server_start_stop():
    """Test server lifecycle."""
    orchestrator = MagicMock()
    server = NeuroPipelineServer("localhost", 50051, orchestrator)

    await server.start()
    assert server.server is not None

    await server.stop(grace=0.1)
