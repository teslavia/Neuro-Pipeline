"""Unit tests for MLX real inference (skipped when mlx_lm unavailable)."""

import pytest
import pytest_asyncio
from pathlib import Path
from src.llm_vlm.mlx_llm_inference import MLXInferenceEngine

try:
    import mlx_lm  # noqa: F401
    HAS_MLX_LM = True
except ImportError:
    HAS_MLX_LM = False

try:
    import mlx_vlm  # noqa: F401
    HAS_MLX_VLM = True
except ImportError:
    HAS_MLX_VLM = False

skip_no_mlx = pytest.mark.skipif(not HAS_MLX_LM, reason="mlx_lm not installed")
skip_no_vlm = pytest.mark.skipif(not HAS_MLX_VLM, reason="mlx_vlm not installed")

MODEL_PATH = Path("models/Llama-3.2-3B-Instruct-4bit-mlx")
VLM_MODEL_PATH = Path("models/Qwen2-VL-2B-Instruct-4bit-mlx")


@pytest.fixture
def model_path():
    return MODEL_PATH


@pytest_asyncio.fixture
async def engine(model_path):
    if not model_path.exists():
        pytest.skip("Model not downloaded")
    if not HAS_MLX_LM:
        pytest.skip("mlx_lm not installed")

    eng = MLXInferenceEngine(model_path)
    await eng.load_model()
    yield eng
    await eng.unload_model()


@skip_no_mlx
@pytest.mark.asyncio
async def test_load_model(model_path):
    """Test model loading."""
    if not model_path.exists():
        pytest.skip("Model not downloaded")

    eng = MLXInferenceEngine(model_path)
    await eng.load_model()

    assert eng.model is not None
    assert eng.tokenizer is not None
    assert eng.use_stub is False


@skip_no_mlx
@pytest.mark.asyncio
async def test_generate_text(engine):
    """Test text generation."""
    prompt = "Analyze this scene: person detected at coordinates (0.3, 0.4) to (0.6, 0.8)."
    response = await engine.generate(prompt, max_tokens=50)

    assert isinstance(response, str)
    assert len(response) > 0


@skip_no_mlx
@pytest.mark.asyncio
async def test_generate_with_temperature(engine):
    """Test generation with different temperature."""
    prompt = "Describe safety concerns."
    response = await engine.generate(prompt, max_tokens=30, temperature=0.5)

    assert isinstance(response, str)


@skip_no_mlx
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
    eng = MLXInferenceEngine(MODEL_PATH)

    with pytest.raises(RuntimeError, match="Model not loaded"):
        await eng.generate("test")


@pytest.mark.asyncio
async def test_model_path_not_found():
    """Test error when model path doesn't exist."""
    eng = MLXInferenceEngine(Path("models/nonexistent"))

    with pytest.raises(FileNotFoundError):
        await eng.load_model()


# ── VLM Real Inference Tests ───────────────────────────────────────────────


@pytest_asyncio.fixture
async def vlm_engine():
    if not HAS_MLX_VLM:
        pytest.skip("mlx_vlm not installed")
    if not VLM_MODEL_PATH.exists():
        pytest.skip("VLM model not downloaded")
    if not MODEL_PATH.exists():
        pytest.skip("LLM model not downloaded (needed as base)")

    eng = MLXInferenceEngine(
        MODEL_PATH, mode="vlm", vlm_model_path=VLM_MODEL_PATH
    )
    await eng.load_model()
    yield eng
    await eng.unload_model()


@skip_no_vlm
@pytest.mark.asyncio
async def test_vlm_model_loads(vlm_engine):
    """VLM model loads alongside LLM."""
    assert vlm_engine.vlm_model is not None
    assert vlm_engine.vlm_processor is not None
    assert vlm_engine.mode == "vlm"


@skip_no_vlm
@pytest.mark.asyncio
async def test_vlm_analyze_real_image(vlm_engine):
    """VLM produces meaningful output for a real image."""
    from PIL import Image
    import io

    # Create a simple test image (red square)
    img = Image.new("RGB", (224, 224), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_data = buf.getvalue()

    result = await vlm_engine.analyze_image(
        image_data, "Describe what you see in this image.", max_tokens=50
    )
    assert isinstance(result, str)
    assert len(result) > 0
    assert "[STUB]" not in result


@skip_no_vlm
@pytest.mark.asyncio
async def test_vlm_still_generates_text(vlm_engine):
    """VLM engine can still do text-only generation."""
    result = await vlm_engine.generate("Say hello.", max_tokens=20)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_vlm_stub_fallback_no_model():
    """VLM mode falls back to stub when model path doesn't exist."""
    if not MODEL_PATH.exists():
        pytest.skip("LLM model not downloaded")
    if not HAS_MLX_LM:
        pytest.skip("mlx_lm not installed")

    eng = MLXInferenceEngine(
        MODEL_PATH, mode="vlm", vlm_model_path=Path("models/nonexistent-vlm")
    )
    await eng.load_model()

    # VLM model should not be loaded, but LLM should work
    assert eng.vlm_model is None
    result = await eng.analyze_image(b"fake", "Describe.", max_tokens=20)
    assert isinstance(result, str)
    assert len(result) > 0
    await eng.unload_model()
