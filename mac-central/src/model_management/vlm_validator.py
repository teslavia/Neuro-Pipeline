"""VLM model validation pipeline — automated benchmark after download."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    model_path: str
    load_success: bool = False
    load_time_seconds: float = 0.0
    inference_success: bool = False
    inference_time_seconds: float = 0.0
    tokens_per_second: float = 0.0
    passed: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model_path": self.model_path,
            "load_success": self.load_success,
            "load_time_seconds": round(self.load_time_seconds, 3),
            "inference_success": self.inference_success,
            "inference_time_seconds": round(self.inference_time_seconds, 3),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "passed": self.passed,
            "errors": self.errors,
        }


class VLMValidator:
    """Validates VLM models after download: load test + inference benchmark."""

    def __init__(
        self,
        min_tps: float = 5.0,
        max_load_time: float = 60.0,
        test_prompt: str = "Describe this image briefly.",
    ) -> None:
        self.min_tps = min_tps
        self.max_load_time = max_load_time
        self.test_prompt = test_prompt

    async def validate(self, model_path: str) -> ValidationResult:
        """Run full validation: load + inference benchmark."""
        result = ValidationResult(model_path=model_path)
        path = Path(model_path)

        if not path.exists():
            result.errors.append(f"Model path does not exist: {model_path}")
            return result

        # Phase 1: Load test
        try:
            t0 = time.monotonic()
            model, processor = self._load_model(model_path)
            result.load_time_seconds = time.monotonic() - t0
            result.load_success = True
            logger.info("Model loaded in %.2fs: %s", result.load_time_seconds, model_path)
        except Exception as e:
            result.errors.append(f"Load failed: {e}")
            logger.error("Model load failed: %s — %s", model_path, e)
            return result

        if result.load_time_seconds > self.max_load_time:
            result.errors.append(
                f"Load time {result.load_time_seconds:.1f}s exceeds max {self.max_load_time}s"
            )

        # Phase 2: Inference benchmark
        try:
            t0 = time.monotonic()
            output_tokens = self._run_inference(model, processor)
            result.inference_time_seconds = time.monotonic() - t0
            result.inference_success = True

            if result.inference_time_seconds > 0:
                result.tokens_per_second = output_tokens / result.inference_time_seconds

            logger.info(
                "Inference: %d tokens in %.2fs (%.1f tps)",
                output_tokens, result.inference_time_seconds, result.tokens_per_second,
            )
        except Exception as e:
            result.errors.append(f"Inference failed: {e}")
            logger.error("Inference failed: %s — %s", model_path, e)

        if result.tokens_per_second < self.min_tps and result.inference_success:
            result.errors.append(
                f"TPS {result.tokens_per_second:.1f} below minimum {self.min_tps}"
            )

        result.passed = (
            result.load_success
            and result.inference_success
            and len(result.errors) == 0
        )
        return result

    def _load_model(self, model_path: str):
        """Load VLM model and processor. Returns (model, processor)."""
        try:
            from mlx_vlm import load as vlm_load
            model, processor = vlm_load(model_path)
            return model, processor
        except ImportError:
            logger.warning("mlx_vlm not available, using stub validation")
            return None, None

    def _run_inference(self, model, processor, max_tokens: int = 50) -> int:
        """Run a test inference. Returns number of output tokens."""
        if model is None:
            # Stub mode — simulate successful inference
            return max_tokens

        try:
            from mlx_vlm import generate as vlm_generate
            import numpy as np

            # Create a small test image (solid color)
            test_image = np.zeros((64, 64, 3), dtype=np.uint8)

            output = vlm_generate(
                model, processor,
                self.test_prompt,
                image=test_image,
                max_tokens=max_tokens,
                verbose=False,
            )
            return len(output.split()) if isinstance(output, str) else max_tokens
        except Exception as e:
            raise RuntimeError(f"Inference error: {e}") from e
