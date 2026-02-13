#!/usr/bin/env python3
"""Test MLX model loading and inference."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_vlm.mlx_llm_inference import MLXInferenceEngine


async def main():
    model_path = Path(__file__).parent.parent / "models" / "Llama-3.2-3B-Instruct"

    if not model_path.exists():
        print(f"[ERROR] Model not found: {model_path}")
        print("Run: bash scripts/download_model.sh")
        return 1

    engine = MLXInferenceEngine(model_path, quantization="4bit")

    print("[1/3] Loading model...")
    await engine.load_model()

    print("[2/3] Testing text generation...")
    prompt = "Describe what you see in this scene: a person standing near a door."
    result = await engine.generate(prompt, max_tokens=128)
    print(f"Result: {result[:200]}...")

    print("[3/3] Unloading model...")
    await engine.unload_model()
    print("✅ Model test complete")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
