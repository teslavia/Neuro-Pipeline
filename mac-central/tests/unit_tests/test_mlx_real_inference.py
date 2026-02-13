"""Unit tests for MLX real inference."""

import pytest
from pathlib import Path
from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine


@pytest.fixture
def model_path():
    return Path("models/Llama-3.2-3B-Instruct")


@pytest.fixture
async def engine(model_path):
    if not model_path.exists():
        pytest.skip("Model not downloaded")

    engine = MLXInferenceEngine(model_path)
    await engine.load_model()
    yield engine
    await engine.unload_model()


@pytest.mark.asyncio
async def test_load_model(model_path):
    """Test model loading."""
    if not model_path.exists():
        pytest.skip("Model not downloaded")

    engine = MLXInferenceEngine(model_path)
    await engine.load_model()

    assert engine.model is not None
    assert engine.tokenizer is not None
    assert engine.use_stub is False


@pytest.mark.asyncio
async def test_generate_text(engine):
    """Test text generation."""
    prompt = "Analyze this scene: person detected at coordinates (0.3, 0.4) to (0.6, 0.8)."
    response = await engine.generate(prompt, max_tokens=50)

    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_generate_with_temperature(engine):
    """Test generation with different temperature."""
    prompt = "Describe safety concerns."
    response = await engine.generate(prompt, max_tokens=30, temperature=0.5)

    assert isinstance(response, str)


@pytest.mark.asyncio
async def test_analyze_image_text_only(engine):
    """Test image analysis with text-only model."""
    image_data = b"fake_jpeg_data"
    prompt = "Describe the scene."

    response = await engine.analyze_image(image_data, prompt, max_tokens=30)

    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_model_not_loaded_error():
    """Test error when model not loaded."""
    engine = MLXInferenceEngine(Path("models/Llama-3.2-3B-Instruct"))

    with pytest.raises(RuntimeError, match="Model not loaded"):
        await engine.generate("test")


@pytest.mark.asyncio
async def test_model_path_not_found():
    """Test error when model path doesn't exist."""
    engine = MLXInferenceEngine(Path("models/nonexistent"))

    with pytest.raises(FileNotFoundError):
        await engine.load_model()
