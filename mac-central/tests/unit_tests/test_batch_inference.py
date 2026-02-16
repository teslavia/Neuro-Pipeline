"""Tests for batch VLM inference."""

import pytest

from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine


class TestBatchInference:
    @pytest.mark.asyncio
    async def test_batch_analyze_stub(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        engine = MLXInferenceEngine(model_dir)
        engine._loaded = True
        engine.use_stub = True
        items = [
            {"frame_data": b"\xff\xd8", "prompt": "describe scene"},
            {"frame_data": b"\xff\xd8", "prompt": "analyze person"},
            {"frame_data": b"\xff\xd8", "prompt": "check fire"},
        ]
        results = await engine.batch_analyze(items)
        assert len(results) == 3
        for i, r in enumerate(results):
            assert f"batch {i}" in r

    @pytest.mark.asyncio
    async def test_batch_analyze_empty(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        engine = MLXInferenceEngine(model_dir)
        engine._loaded = True
        engine.use_stub = True
        results = await engine.batch_analyze([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_analyze_single_item(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        engine = MLXInferenceEngine(model_dir)
        engine._loaded = True
        engine.use_stub = True
        results = await engine.batch_analyze([
            {"frame_data": b"\xff\xd8", "prompt": "test"}
        ])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_batch_analyze_not_loaded(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        engine = MLXInferenceEngine(model_dir)
        with pytest.raises(RuntimeError, match="not loaded"):
            await engine.batch_analyze([{"frame_data": b"", "prompt": "test"}])

    @pytest.mark.asyncio
    async def test_batch_analyze_prompt_in_result(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        engine = MLXInferenceEngine(model_dir)
        engine._loaded = True
        engine.use_stub = True
        results = await engine.batch_analyze([
            {"frame_data": b"\xff\xd8", "prompt": "hello world"},
        ])
        assert "hello world" in results[0]
