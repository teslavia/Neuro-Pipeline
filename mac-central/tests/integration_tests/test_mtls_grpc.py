"""Integration test: mTLS gRPC connection — TLS enabled + disabled modes."""

import asyncio
import tempfile

import grpc
import pytest
import pytest_asyncio

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.generated import neuro_pipeline_pb2, neuro_pipeline_pb2_grpc
from src.communication.grpc_server import NeuroPipelineServer
from src.application_logic.central_orchestrator import CentralOrchestrator
from src.config import TLSConfig


CERT_DIR = Path(__file__).resolve().parents[3] / "certs"


def _certs_available() -> bool:
    return all(
        (CERT_DIR / f).exists()
        for f in ("ca.pem", "server.pem", "server-key.pem", "client.pem", "client-key.pem")
    )


skip_no_certs = pytest.mark.skipif(not _certs_available(), reason="certs/ not generated")


def _make_orchestrator():
    orch = CentralOrchestrator(Path("models/test"))
    orch.inference_engine = MagicMock()
    orch.inference_engine.load_model = AsyncMock()
    orch.inference_engine.unload_model = AsyncMock()
    orch.inference_engine.analyze_image = AsyncMock(return_value="stub")
    return orch


# ── Insecure mode ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def insecure_server():
    orch = _make_orchestrator()
    srv = NeuroPipelineServer("localhost", 50199, orch)
    await srv.start()
    channel = grpc.aio.insecure_channel("localhost:50199")
    yield channel
    await channel.close()
    await srv.stop(grace=0.1)


@pytest.mark.asyncio
async def test_insecure_health_check(insecure_server):
    """HealthCheck works over insecure channel."""
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(insecure_server)
    resp = await stub.HealthCheck(
        neuro_pipeline_pb2.HealthCheckRequest(client_id="test-insecure")
    )
    assert resp.status == neuro_pipeline_pb2.HealthCheckResponse.SERVING
    assert resp.version == "2.2.0"


# ── mTLS mode ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def mtls_server():
    if not _certs_available():
        pytest.skip("certs/ not generated")
    tls_cfg = TLSConfig(
        enabled=True,
        ca_cert=str(CERT_DIR / "ca.pem"),
        server_cert=str(CERT_DIR / "server.pem"),
        server_key=str(CERT_DIR / "server-key.pem"),
    )
    orch = _make_orchestrator()
    srv = NeuroPipelineServer("localhost", 50200, orch, tls_config=tls_cfg)
    await srv.start()

    ca = (CERT_DIR / "ca.pem").read_bytes()
    client_cert = (CERT_DIR / "client.pem").read_bytes()
    client_key = (CERT_DIR / "client-key.pem").read_bytes()
    creds = grpc.ssl_channel_credentials(ca, client_key, client_cert)
    channel = grpc.aio.secure_channel("localhost:50200", creds)
    yield channel
    await channel.close()
    await srv.stop(grace=0.1)


@skip_no_certs
@pytest.mark.asyncio
async def test_mtls_health_check(mtls_server):
    """HealthCheck works over mTLS secure channel."""
    stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(mtls_server)
    resp = await stub.HealthCheck(
        neuro_pipeline_pb2.HealthCheckRequest(client_id="test-mtls")
    )
    assert resp.status == neuro_pipeline_pb2.HealthCheckResponse.SERVING


@skip_no_certs
@pytest.mark.asyncio
async def test_mtls_rejects_no_client_cert():
    """Server with mTLS rejects connections without client certificate."""
    tls_cfg = TLSConfig(
        enabled=True,
        ca_cert=str(CERT_DIR / "ca.pem"),
        server_cert=str(CERT_DIR / "server.pem"),
        server_key=str(CERT_DIR / "server-key.pem"),
    )
    orch = _make_orchestrator()
    srv = NeuroPipelineServer("localhost", 50201, orch, tls_config=tls_cfg)
    await srv.start()

    try:
        # Connect with CA only (no client cert) — should fail
        ca = (CERT_DIR / "ca.pem").read_bytes()
        creds = grpc.ssl_channel_credentials(ca)
        channel = grpc.aio.secure_channel("localhost:50201", creds)
        stub = neuro_pipeline_pb2_grpc.NeuroPipelineServiceStub(channel)

        with pytest.raises(grpc.aio.AioRpcError):
            await stub.HealthCheck(
                neuro_pipeline_pb2.HealthCheckRequest(client_id="no-cert")
            )
        await channel.close()
    finally:
        await srv.stop(grace=0.1)
