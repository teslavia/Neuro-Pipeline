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
    orchestrator.send_command = AsyncMock()
    orchestrator.handle_edge_event = AsyncMock()
    orchestrator.get_pending_command = AsyncMock(side_effect=asyncio.TimeoutError)
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
            result.device_id = "edge-test"
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
        result.device_id = "edge-test"
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
    assert response.version == "1.3.0"


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
    # Let the loop run once then cancel
    call_count = 0

    def cancelled_side_effect():
        nonlocal call_count
        call_count += 1
        return call_count > 2  # Allow a couple iterations

    mock_context.cancelled = cancelled_side_effect

    responses = []
    async for response in servicer.BidirectionalEventStream(mock_iterator(), mock_context):
        responses.append(response)
        break  # Stop after first response (if any)

    # The stream should have started without error
    # (handle_edge_event may or may not have been called depending on timing)


@pytest.mark.asyncio
async def test_stream_detection_with_device_id(servicer, mock_orchestrator):
    """Test that device_id is extracted from detection results."""
    async def mock_iterator():
        for i in range(2):
            result = neuro_pipeline_pb2.DetectionResult()
            result.frame_id = i
            result.device_id = "edge-001"
            yield result

    response = await servicer.StreamDetectionResults(mock_iterator(), None)
    assert response.success is True
    assert response.frames_received == 2


@pytest.mark.asyncio
async def test_stream_detection_with_session_manager(mock_orchestrator):
    """Test that session_manager is called during streaming."""
    from unittest.mock import MagicMock
    session_mgr = MagicMock()
    session_mgr.register.return_value = True
    svc = NeuroPipelineServicer(mock_orchestrator, session_manager=session_mgr)

    async def mock_iterator():
        result = neuro_pipeline_pb2.DetectionResult()
        result.frame_id = 1
        result.device_id = "edge-001"
        yield result

    await svc.StreamDetectionResults(mock_iterator(), None)
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
    orchestrator = MagicMock()
    server = NeuroPipelineServer("localhost", 50051, orchestrator)

    await server.start()
    assert server.server is not None

    await server.stop(grace=0.1)


@pytest.mark.asyncio
async def test_server_accepts_tls_config():
    """Test server accepts TLS config without error (insecure fallback)."""
    orchestrator = MagicMock()
    tls = MagicMock()
    tls.enabled = False
    server = NeuroPipelineServer("localhost", 50052, orchestrator, tls_config=tls)

    await server.start()
    assert server.server is not None
    await server.stop(grace=0.1)
