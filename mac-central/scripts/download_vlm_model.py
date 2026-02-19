#!/usr/bin/env python3
"""Download and optionally quantize VLM models for MLX inference.

This script supports two modes:
1. Download pre-converted models from MLX community (default, faster)
2. Download original models and convert/quantize locally (more flexible)

Usage:
    # Download pre-converted model (recommended)
    python scripts/download_vlm_model.py

    # Download and quantize locally
    python scripts/download_vlm_model.py --quantize --qbits 4

    # Download specific model and quantize
    python scripts/download_vlm_model.py --model Qwen/Qwen2-VL-7B-Instruct --quantize --qbits 8

Note: VLM models require torch and torchvision for image processing.
      Install with: pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
"""

import argparse
import subprocess
import sys
from pathlib import Path


def check_dependencies(require_conversion: bool = False) -> None:
    """Check that required dependencies are installed.

    Args:
        require_conversion: If True, check for conversion dependencies (mlx-vlm with convert)
    """
    missing = []
    warnings = []

    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        missing.append("huggingface-hub")

    try:
        import mlx_vlm  # noqa: F401
    except ImportError:
        missing.append("mlx-vlm")

    # Check for torch/torchvision (required for VLM image processing)
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")

    try:
        import torchvision  # noqa: F401
    except ImportError:
        warnings.append("torchvision not found - VLM may not work properly. Install with: pip install torchvision")

    if missing:
        print("[ERROR] Missing dependencies:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nInstall with:")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)

    for w in warnings:
        print(f"[WARN] {w}")


def download_preconverted_model(model: str, output: str) -> Path:
    """Download pre-converted VLM model from HuggingFace MLX community.

    Args:
        model: HuggingFace model ID (e.g., mlx-community/Qwen2-VL-2B-Instruct-4bit)
        output: Output directory path

    Returns:
        Path to the model directory
    """
    output_path = Path(output)

    if output_path.exists():
        if (output_path / "config.json").exists() and (output_path / "model.safetensors").exists():
            print(f"[INFO] Model already exists at {output_path}")
            return output_path
        else:
            print("[WARN] Incomplete model directory, re-downloading...")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("[1/2] Downloading pre-converted MLX model...")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=model,
            local_dir=str(output_path),
        )
        print(f"      Downloaded to: {output_path}")
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        sys.exit(1)

    return output_path


def download_and_convert_model(
    model: str,
    output: str,
    quantize: bool = True,
    qbits: int = 4,
    q_group_size: int = 64,
    dtype: str = "float16",
) -> Path:
    """Download original model and convert/quantize for MLX.

    Args:
        model: HuggingFace model ID (e.g., Qwen/Qwen2-VL-2B-Instruct)
        output: Output directory path
        quantize: Whether to quantize the model
        qbits: Quantization bits (4 or 8)
        q_group_size: Group size for quantization
        dtype: Data type for non-quantized layers

    Returns:
        Path to the converted model directory
    """
    output_path = Path(output)

    if output_path.exists():
        if (output_path / "config.json").exists() and (output_path / "model.safetensors").exists():
            print(f"[INFO] Model already exists at {output_path}")
            return output_path
        else:
            print("[WARN] Incomplete model directory, removing and re-converting...")
            import shutil
            shutil.rmtree(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("  VLM Model Converter for MLX")
    print("=" * 50)
    print(f"Source: {model}")
    print(f"Target: {output_path}")
    print(f"Quantize: {quantize} ({qbits}-bit, group_size={q_group_size})" if quantize else f"Quantize: No (dtype={dtype})")
    print()

    # Step 1: Download from HuggingFace
    print("[1/3] Downloading original model from HuggingFace...")
    try:
        from huggingface_hub import snapshot_download
        cache_path = snapshot_download(repo_id=model)
        print(f"      Cached at: {cache_path}")
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        sys.exit(1)

    # Step 2: Convert to MLX format
    print("[2/3] Converting to MLX format...")
    convert_cmd = [
        sys.executable, "-m", "mlx_vlm", "convert",
        "--hf-path", model,
        "--mlx-path", str(output_path),
        "--dtype", dtype,
    ]

    if quantize:
        convert_cmd.extend([
            "--quantize",
            "--q-bits", str(qbits),
            "--q-group-size", str(q_group_size),
        ])

    try:
        result = subprocess.run(convert_cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"      {line}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Conversion failed:")
        if e.stderr:
            print(e.stderr)
        sys.exit(1)

    return output_path


def verify_model(output_path: Path) -> bool:
    """Verify model files are present."""
    print("[3/3] Verifying model files...")
    required_files = ["config.json"]
    missing = [f for f in required_files if not (output_path / f).exists()]

    if missing:
        print(f"[ERROR] Missing required files: {missing}")
        return False

    # Check for model weights
    has_weights = (
        (output_path / "model.safetensors").exists() or
        (output_path / "weights.safetensors").exists() or
        list(output_path.glob("*.safetensors"))
    )

    if not has_weights:
        print("[ERROR] No model weight files found")
        return False

    return True


def test_model_load(model_path: str) -> bool:
    """Test that the model can be loaded."""
    print()
    print("[TEST] Verifying model can be loaded...")
    try:
        from mlx_vlm import load
        model, processor = load(model_path, processor_args={'trust_remote_code': True})
        print("[TEST] Model loaded successfully!")
        return True
    except Exception as e:
        print(f"[TEST] Warning: Could not load model: {e}")
        return False


def test_model_inference(model_path: str) -> bool:
    """Test that the model can generate text."""
    print()
    print("[TEST] Running inference test...")
    try:
        from mlx_vlm import load, generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config

        model, processor = load(model_path, processor_args={'trust_remote_code': True})
        config = load_config(model_path)

        messages = [{'role': 'user', 'content': 'Say hello in 5 words.'}]
        prompt = apply_chat_template(processor, config, messages)

        output = generate(model, processor, prompt=prompt, verbose=False, max_tokens=30)
        print(f"[TEST] Response: {output.text}")
        print(f"[TEST] Speed: {output.generation_tps:.1f} tokens/sec")
        print("[TEST] Inference test passed!")
        return True
    except Exception as e:
        print(f"[TEST] Inference test failed: {e}")
        return False


def get_model_size(output_path: Path) -> float:
    """Calculate total model size in GB."""
    total_size = sum(f.stat().st_size for f in output_path.rglob("*") if f.is_file())
    return total_size / (1024 ** 3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and optionally quantize VLM models for MLX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download pre-converted 4-bit model (fast, recommended)
  python scripts/download_vlm_model.py

  # Download pre-converted 8-bit model
  python scripts/download_vlm_model.py --prebuilt-8bit

  # Download and quantize 2B model locally
  python scripts/download_vlm_model.py --model Qwen/Qwen2-VL-2B-Instruct --quantize --qbits 4

  # Download and quantize 7B model with 8-bit
  python scripts/download_vlm_model.py --model Qwen/Qwen2-VL-7B-Instruct --quantize --qbits 8

  # Download without quantization (larger but more accurate)
  python scripts/download_vlm_model.py --model Qwen/Qwen2-VL-2B-Instruct --no-quantize

  # Test existing model
  python scripts/download_vlm_model.py --test-only --output models/Qwen2-VL-2B-Instruct-4bit-mlx

Pre-built MLX models available:
  - mlx-community/Qwen2-VL-2B-Instruct-4bit (1.2GB, fast)
  - mlx-community/Qwen2-VL-2B-Instruct-8bit (larger, more accurate)
  - mlx-community/Qwen2-VL-7B-Instruct-4bit (4.3GB, best quality)

Quantization options:
  --qbits 4       4-bit quantization (smallest, fastest)
  --qbits 8       8-bit quantization (larger, more accurate)
  --q-group-size  Group size for quantization (default: 64)

Note: VLM inference requires torch and torchvision for image processing.
        """,
    )

    # Model selection
    parser.add_argument(
        "--model",
        default=None,
        help="HuggingFace model ID to convert (e.g., Qwen/Qwen2-VL-2B-Instruct). "
             "If not specified, downloads pre-built model.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (auto-generated if not specified)",
    )

    # Pre-built model options
    parser.add_argument(
        "--prebuilt-2bit",
        action="store_true",
        help="Download pre-built 2B 4-bit model (default)",
    )
    parser.add_argument(
        "--prebuilt-7bit",
        action="store_true",
        help="Download pre-built 7B 4-bit model",
    )
    parser.add_argument(
        "--prebuilt-8bit",
        action="store_true",
        help="Download pre-built 2B 8-bit model",
    )

    # Quantization options (for local conversion)
    parser.add_argument(
        "--quantize",
        action="store_true",
        default=True,
        help="Quantize the model (default: True when converting)",
    )
    parser.add_argument(
        "--no-quantize",
        action="store_true",
        help="Disable quantization",
    )
    parser.add_argument(
        "--qbits",
        type=int,
        default=4,
        choices=[4, 8],
        help="Quantization bits (default: 4)",
    )
    parser.add_argument(
        "--q-group-size",
        type=int,
        default=64,
        help="Group size for quantization (default: 64)",
    )
    parser.add_argument(
        "--dtype",
        type=str,
        default="float16",
        choices=["float16", "bfloat16", "float32"],
        help="Data type for non-quantized layers (default: float16)",
    )

    # Testing options
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test model loading after download",
    )
    parser.add_argument(
        "--test-inference",
        action="store_true",
        help="Test inference after download (implies --test)",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Only test existing model, don't download",
    )

    args = parser.parse_args()

    # Determine mode: pre-built or local conversion
    use_prebuilt = args.model is None

    # Set default output path and model based on options
    if use_prebuilt:
        if args.prebuilt_7bit:
            model = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
            default_output = "models/Qwen2-VL-7B-Instruct-4bit-mlx"
        elif args.prebuilt_8bit:
            model = "mlx-community/Qwen2-VL-2B-Instruct-8bit"
            default_output = "models/Qwen2-VL-2B-Instruct-8bit-mlx"
        else:
            model = "mlx-community/Qwen2-VL-2B-Instruct-4bit"
            default_output = "models/Qwen2-VL-2B-Instruct-4bit-mlx"
    else:
        model = args.model
        # Auto-generate output path
        quantize = args.quantize and not args.no_quantize
        if quantize:
            default_output = f"models/{model.split('/')[-1]}-{args.qbits}bit-mlx"
        else:
            default_output = f"models/{model.split('/')[-1]}-mlx"

    output = args.output or default_output
    output_path = Path(output)

    # Check dependencies
    check_dependencies(require_conversion=not use_prebuilt)

    # Test-only mode
    if args.test_only:
        if not output_path.exists():
            print(f"[ERROR] Model not found at {output_path}")
            sys.exit(1)
        print(f"Testing existing model at {output_path}")
        success = test_model_load(str(output_path))
        if args.test_inference:
            success = test_model_inference(str(output_path)) and success
        sys.exit(0 if success else 1)

    print("=" * 50)
    print("  VLM Model Downloader for MLX")
    print("=" * 50)
    print(f"Mode: {'Pre-built' if use_prebuilt else 'Local conversion'}")
    print(f"Source: {model}")
    print(f"Target: {output_path}")
    print()

    # Download/convert model
    if use_prebuilt:
        output_path = download_preconverted_model(model, output)
    else:
        quantize = args.quantize and not args.no_quantize
        output_path = download_and_convert_model(
            model=model,
            output=output,
            quantize=quantize,
            qbits=args.qbits,
            q_group_size=args.q_group_size,
            dtype=args.dtype,
        )

    # Verify
    if not verify_model(output_path):
        sys.exit(1)

    # Calculate size
    size_gb = get_model_size(output_path)

    print()
    print("=" * 50)
    print("  Download Complete")
    print("=" * 50)
    print(f"Model path: {output_path}")
    print(f"Size: {size_gb:.2f} GB")
    print()
    print("Update config.yaml to use this model:")
    print("  central:")
    print(f'    vlm_model_path: "{output}"')
    print('    inference_mode: "vlm"')

    # Test if requested
    if args.test or args.test_inference:
        test_model_load(str(output_path))
        if args.test_inference:
            test_model_inference(str(output_path))


if __name__ == "__main__":
    main()
