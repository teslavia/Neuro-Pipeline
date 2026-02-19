"""
MLX-based LLM/VLM inference engine for Apple Silicon.

Supports two modes:
  - "llm": text-only via mlx_lm (default, existing behavior)
  - "vlm": vision-language via mlx_vlm (Qwen2-VL, etc.)
"""

import logging
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from src.exceptions import ModelLoadError, InferenceError

logger = logging.getLogger(__name__)


class ConversationContext:
    """Multi-turn conversation history per device."""

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._history: List[Dict[str, str]] = []

    def add_turn(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        if len(self._history) > self.max_turns * 2:
            self._history = self._history[-self.max_turns * 2:]

    def build_prompt(self, new_prompt: str) -> str:
        """Build a multi-turn prompt string from history + new prompt."""
        parts = []
        for turn in self._history:
            prefix = "User" if turn["role"] == "user" else "Assistant"
            parts.append(f"{prefix}: {turn['content']}")
        parts.append(f"User: {new_prompt}")
        return "\n".join(parts)

    def clear(self) -> None:
        self._history.clear()

    @property
    def turn_count(self) -> int:
        return len(self._history) // 2


class MLXInferenceEngine:
    """MLX-based inference engine for Apple Silicon UMA."""

    def __init__(
        self,
        model_path: Path,
        quantization: str = "4bit",
        mode: str = "llm",
        vlm_model_path: Optional[Path] = None,
    ) -> None:
        self.model_path = model_path
        self.quantization = quantization
        self.mode = mode
        self.vlm_model_path = vlm_model_path
        self.model = None
        self.tokenizer = None
        self.vlm_model = None
        self.vlm_processor = None
        self.use_stub = True
        self._loaded = False
        self._conversations: Dict[str, ConversationContext] = {}
        logger.info(
            f"MLXInferenceEngine created: path={model_path}, "
            f"quant={quantization}, mode={mode}"
        )

    async def load_model(self) -> None:
        """Load model into unified memory. Falls back to stub mode if unavailable."""
        if not self.model_path.exists():
            logger.warning(f"Model path not found: {self.model_path} — running in stub mode")
            self.use_stub = True
            self._loaded = True
            return

        # Load LLM (text) model
        try:
            import mlx.core as mx
            from mlx_lm import load

            logger.info(f"Loading MLX LLM from {self.model_path}...")
            self.model, self.tokenizer = load(str(self.model_path))
            self.use_stub = False
            logger.info(f"LLM loaded (MLX device: {mx.default_device()})")
        except ImportError:
            logger.warning("mlx_lm not installed, running in stub mode")
            self.use_stub = True
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Failed to load LLM: {e}")
            raise ModelLoadError(f"LLM load failed: {e}") from e

        # Load VLM model if mode=vlm and path provided
        if self.mode == "vlm" and self.vlm_model_path:
            try:
                from mlx_vlm import load as vlm_load

                vlm_path = self.vlm_model_path
                if not vlm_path.exists():
                    logger.warning(f"VLM model path not found: {vlm_path}")
                else:
                    logger.info(f"Loading MLX VLM from {vlm_path}...")
                    self.vlm_model, self.vlm_processor = vlm_load(str(vlm_path))
                    logger.info("VLM loaded successfully")
            except ImportError:
                logger.warning("mlx_vlm not installed, VLM disabled")
            except (OSError, RuntimeError, ValueError) as e:
                logger.error(f"Failed to load VLM: {e}")

        self._loaded = True

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate text from prompt using MLX LLM."""
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if self.use_stub:
            logger.debug(f"[STUB] Generating response for prompt ({len(prompt)} chars)")
            return f"[STUB] Analysis of: {prompt[:80]}"

        if not self.model:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            from mlx_lm import generate as mlx_generate

            t0 = time.perf_counter()
            response = mlx_generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                verbose=False,
            )
            t1 = time.perf_counter()
            logger.info(f"[Perf] MLX LLM inference: {(t1-t0)*1000:.1f}ms")
            return response
        except (RuntimeError, ValueError) as e:
            logger.error(f"LLM generation failed: {e}")
            raise InferenceError(f"LLM generation failed: {e}") from e

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str,
        max_tokens: int = 256,
    ) -> str:
        """Analyze image with VLM or fall back to text-only LLM."""
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if self.use_stub:
            return await self.generate(prompt, max_tokens=max_tokens)

        # VLM mode: real image understanding
        if self.mode == "vlm" and self.vlm_model and self.vlm_processor:
            try:
                from mlx_vlm import generate as vlm_generate
                from PIL import Image
                import io

                image = Image.open(io.BytesIO(image_data))
                t0 = time.perf_counter()
                result = vlm_generate(
                    self.vlm_model,
                    self.vlm_processor,
                    image,
                    prompt,
                    max_tokens=max_tokens,
                    verbose=False,
                )
                t1 = time.perf_counter()
                logger.info(f"[Perf] MLX VLM inference: {(t1-t0)*1000:.1f}ms")
                return result
            except (RuntimeError, ValueError, OSError) as e:
                logger.error(f"VLM inference failed, falling back to LLM: {e}")

        # Fallback: text-only
        logger.info(f"Text-only mode, ignoring image ({len(image_data)} bytes)")
        return await self.generate(prompt, max_tokens=max_tokens)

    async def batch_analyze(
        self,
        items: list,
        max_tokens: int = 256,
    ) -> list:
        """Batch analyze multiple items. Each item is a dict with 'frame_data' and 'prompt'.

        Returns list of result strings, one per item.
        Falls back to sequential analyze_image if batch processing fails.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if self.use_stub:
            return [f"[STUB] batch {i}: {item.get('prompt', '')[:60]}"
                    for i, item in enumerate(items)]

        # Real batch: process sequentially (VLM is the bottleneck, not batching)
        results = []
        for item in items:
            try:
                result = await self.analyze_image(
                    item["frame_data"], item["prompt"], max_tokens=max_tokens
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Batch item failed: {e}")
                results.append(f"[ERROR] {e}")
        return results

    async def unload_model(self) -> None:
        """Unload all models from memory."""
        self.model = None
        self.tokenizer = None
        self.vlm_model = None
        self.vlm_processor = None
        self._loaded = False
        self._conversations.clear()
        logger.info("Models unloaded")

    async def switch_vlm_model(self, model_path: str) -> bool:
        """Hot-swap the VLM model at runtime. Returns True on success."""
        new_path = Path(model_path)
        if not new_path.exists():
            logger.error("VLM switch failed: path not found: %s", model_path)
            return False

        try:
            from mlx_vlm import load as vlm_load
            logger.info("Switching VLM model to %s...", model_path)
            new_model, new_processor = vlm_load(str(new_path))
            # Swap atomically
            old_model = self.vlm_model
            self.vlm_model = new_model
            self.vlm_processor = new_processor
            self.vlm_model_path = new_path
            del old_model  # free old model memory
            logger.info("VLM model switched to %s", model_path)
            return True
        except ImportError:
            logger.warning("mlx_vlm not installed, cannot switch VLM model")
            return False
        except (OSError, RuntimeError, ValueError) as e:
            logger.error("VLM switch failed: %s", e)
            return False

    def get_conversation(self, device_id: str, max_turns: int = 10) -> ConversationContext:
        """Get or create a conversation context for a device."""
        if device_id not in self._conversations:
            self._conversations[device_id] = ConversationContext(max_turns=max_turns)
        return self._conversations[device_id]

    def clear_conversation(self, device_id: str) -> None:
        """Clear conversation history for a device."""
        if device_id in self._conversations:
            self._conversations[device_id].clear()
