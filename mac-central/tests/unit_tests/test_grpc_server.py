"""Unit tests for gRPC server."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.communication.grpc_server import NeuroPipelineServicer, NeuroPipelineServer
from src.generated import neuro_pipeline_pb2
from tests.factories import make_orchestrator, make_detection_stream


@pytest.fixture
def mock_orchestrator():
    return make_orchestrator()


@pytest.fixture
def servicer(mock_orchestrator):
    return NeuroPipelineServicer(mock_orchestrator)


@pytest.mark.asyncio
async def test_stream_detection_results_success(servicer, mock_orchestrator):
    """Test successful detection result streaming."""
    response = await servicer.StreamDetectionResults(make_detection_stream(3), None)

    assert response.success is True
    assert response.frames_received == 3
    assert mock_orchestrator.process_detection.call_count == 3


@pytest.mark.asyncio
async def test_stream_detection_results_error(servicer, mock_orchestrator):
    """Test detection streaming with processing error."""
    mock_orchestrator.process_detection.side_effect = Exception("Processing failed")

    response = await servicer.StreamDetectionResults(make_detection_stream(1), None)

    assert response.success is False
    assert "Processing failed" in response.message


@pytest.mark.asyncio
async def test_health_check(servicer):
    """Test health check endpoint."""
    request = neuro_pipeline_pb2.HealthCheckRequest()
    request.client_id = "test_client"

    response = await servicer.HealthCheck(request, None)

    assert response.status == neuro_pipeline_pb2.HealthCheckResponse.SERVING
    assert response.version == "2.4.1"


@pytest.mark.asyncio
async def test_send_control_command(servicer, mock_orchestrator):
    """Test control command handling routes to orchestrator."""
    request = neuro_pipeline_pb2.ControlCommand()
    request.type = neuro_pipeline_pb2.ControlCommand.SET_FPS
    request.command_id = 123

    response = await servicer.SendControlCommand(request, None)

    assert response.success is True
    assert response.command_id == 123
    mock_orchestrator.send_command.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_bidirectional_event_stream(servicer, mock_orchestrator):
    """Test bidirectional event streaming processes events."""
    async def mock_iterator():
        event = neuro_pipeline_pb2.EdgeEvent()
        event.type = neuro_pipeline_pb2.EdgeEvent.DETECTION_ALERT
        event.timestamp_us = 1000
        yield event

    mock_context = MagicMock()
    call_count = 0

    def cancelled_side_effect():
        nonlocal call_count
        call_count += 1
        return call_count > 2

    mock_context.cancelled = cancelled_side_effect

    responses = []
    async for response in servicer.BidirectionalEventStream(mock_iterator(), mock_context):
        responses.append(response)
        break


@pytest.mark.asyncio
async def test_stream_detection_with_device_id(servicer, mock_orchestrator):
    """Test that device_id is extracted from detection results."""
    response = await servicer.StreamDetectionResults(
        make_detection_stream(2, device_id="edge-001"), None
    )
    assert response.success is True
    assert response.frames_received == 2


@pytest.mark.asyncio
async def test_stream_detection_with_session_manager(mock_orchestrator):
    """Test that session_manager is called during streaming."""
    session_mgr = MagicMock()
    session_mgr.register.return_value = True
    svc = NeuroPipelineServicer(mock_orchestrator, session_manager=session_mgr)

    await svc.StreamDetectionResults(
        make_detection_stream(1, device_id="edge-001"), None
    )
    session_mgr.register.assert_called_once_with("edge-001")
    session_mgr.heartbeat.assert_called_once_with("edge-001")
    session_mgr.increment_frames.assert_called_once_with("edge-001")
    session_mgr.unregister.assert_called_once_with("edge-001")


@pytest.mark.asyncio
async def test_register_device(servicer):
    """Test RegisterDevice RPC."""
    request = neuro_pipeline_pb2.DeviceRegistration()
    request.device_id = "edge-001"
    request.device_name = "Rock 5B"
    request.firmware_version = "1.0.0"

    response = await servicer.RegisterDevice(request, None)
    assert response.success is True
    assert response.assigned_id == "edge-001"


@pytest.mark.asyncio
async def test_server_start_stop():
    """Test server lifecycle."""
    server = NeuroPipelineServer("localhost", 50051, make_orchestrator())

    await server.start()
    assert server.server is not None

    await server.stop(grace=0.1)


@pytest.mark.asyncio
async def test_server_accepts_tls_config():
    """Test server accepts TLS config without error (insecure fallback)."""
    tls = MagicMock()
    tls.enabled = False
    server = NeuroPipelineServer("localhost", 50052, make_orchestrator(), tls_config=tls)

    await server.start()
    assert server.server is not None
    await server.stop(grace=0.1)
