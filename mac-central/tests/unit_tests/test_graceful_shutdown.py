"""Tests for graceful shutdown behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.pipeline.central_orchestrator import CentralOrchestrator


@pytest_asyncio.fixture
async def orchestrator(tmp_path):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    orch = CentralOrchestrator(model_dir)
    # Mock the inference engine to avoid real model loading
    mock_engine = MagicMock()
    mock_engine.load_model = AsyncMock()
    mock_engine.unload_model = AsyncMock()
    mock_engine._loaded = True
    mock_engine.get_conversation = MagicMock()
    mock_engine.analyze_image = AsyncMock(return_value="[STUB] test")
    orch.inference_engine = mock_engine
    orch._vlm_worker_task = asyncio.create_task(orch._vlm_worker())
    yield orch
    if orch._vlm_worker_task and not orch._vlm_worker_task.done():
        orch._vlm_worker_task.cancel()
        try:
            await orch._vlm_worker_task
        except asyncio.CancelledError:
            pass


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_sets_flag(self, orchestrator):
        assert not orchestrator._shutting_down
        await orchestrator.shutdown()
        assert orchestrator._shutting_down

    @pytest.mark.asyncio
    async def test_shutdown_cancels_worker(self, orchestrator):
        await orchestrator.shutdown()
        assert orchestrator._vlm_worker_task.done()

    @pytest.mark.asyncio
    async def test_shutdown_unloads_model(self, orchestrator):
        await orchestrator.shutdown()
        orchestrator.inference_engine.unload_model.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self, orchestrator):
        """Shutdown with empty queue should complete quickly."""
        await asyncio.wait_for(orchestrator.shutdown(), timeout=5.0)

    @pytest.mark.asyncio
    async def test_shutdown_timeout_on_stuck_queue(self, orchestrator):
        """If queue can't drain, shutdown should still complete after timeout."""
        # Cancel the worker so nothing processes the queue
        orchestrator._vlm_worker_task.cancel()
        try:
            await orchestrator._vlm_worker_task
        except asyncio.CancelledError:
            pass
        orchestrator._vlm_worker_task = None
        orchestrator._vlm_queue.put_nowait({"test": True})
        # Shutdown with very short timeout
        await orchestrator.shutdown(timeout=0.1)
        assert orchestrator._shutting_down
