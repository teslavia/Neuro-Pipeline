"""Unit tests for MLX inference engine (stub mode)."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine


class TestMLXInferenceEngine:
    """Tests for MLXInferenceEngine (stub mode via mocked mlx_lm)."""

    @pytest.mark.asyncio
    async def test_create_engine(self, temp_model_dir):
        engine = MLXInferenceEngine(temp_model_dir)
        assert engine.model_path == temp_model_dir
        assert engine.quantization == "4bit"

    @pytest.mark.asyncio
    async def test_load_model_stub(self, temp_model_dir):
        with patch.dict("sys.modules", {"mlx": None, "mlx.core": None, "mlx_lm": None}):
            engine = MLXInferenceEngine(temp_model_dir)
            await engine.load_model()
            assert engine.use_stub is True

    @pytest.mark.asyncio
    async def test_generate_stub(self, temp_model_dir):
        with patch.dict("sys.modules", {"mlx": None, "mlx.core": None, "mlx_lm": None}):
            engine = MLXInferenceEngine(temp_model_dir)
            await engine.load_model()
            result = await engine.generate("Test prompt", max_tokens=64)
            assert isinstance(result, str)
            assert "[STUB]" in result

    @pytest.mark.asyncio
    async def test_analyze_image_stub(self, temp_model_dir):
        with patch.dict("sys.modules", {"mlx": None, "mlx.core": None, "mlx_lm": None}):
            engine = MLXInferenceEngine(temp_model_dir)
            await engine.load_model()
            image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
            result = await engine.analyze_image(image_data, "Describe this image")
            assert isinstance(result, str)
            assert "[STUB]" in result

    @pytest.mark.asyncio
    async def test_unload_model(self, temp_model_dir):
        with patch.dict("sys.modules", {"mlx": None, "mlx.core": None, "mlx_lm": None}):
            engine = MLXInferenceEngine(temp_model_dir)
            await engine.load_model()
            await engine.unload_model()
            assert engine.model is None
            assert engine.tokenizer is None
