#!/usr/bin/env bash
# Convert HuggingFace model to MLX native format with 4-bit quantization.
#
# Usage:
#   LLM:  bash tools/convert_mlx_model.sh [input_dir] [output_dir]
#   VLM:  bash tools/convert_mlx_model.sh --vlm [input_dir] [output_dir]
#
# Requires: pip install mlx-lm   (for LLM)
#           pip install mlx-vlm   (for VLM)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="llm"
if [ "${1:-}" = "--vlm" ]; then
    MODE="vlm"
    shift
fi

if [ "$MODE" = "vlm" ]; then
    INPUT_DIR="${1:-Qwen/Qwen2-VL-2B-Instruct}"
    OUTPUT_DIR="${2:-$REPO_ROOT/mac-central/models/Qwen2-VL-2B-Instruct-4bit-mlx}"
    PKG="mlx_vlm"
    CONVERT_CMD="python3 -m mlx_vlm.convert --hf-path $INPUT_DIR --mlx-path $OUTPUT_DIR -q --q-bits 4"
else
    INPUT_DIR="${1:-$REPO_ROOT/mac-central/models/Llama-3.2-3B-Instruct}"
    OUTPUT_DIR="${2:-$REPO_ROOT/mac-central/models/Llama-3.2-3B-Instruct-4bit-mlx}"
    PKG="mlx_lm"
    CONVERT_CMD="python3 -m mlx_lm.convert --hf-path $INPUT_DIR --mlx-path $OUTPUT_DIR -q --q-bits 4"
fi

echo "=== MLX Model Conversion ($MODE) ==="
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_DIR"
echo "Quantization: 4-bit"
echo ""

if ! python3 -c "import $PKG" 2>/dev/null; then
    echo "ERROR: $PKG not installed. Run: pip install $PKG"
    exit 1
fi

eval "$CONVERT_CMD"

echo ""
echo "=== Conversion Complete ==="
echo "Output: $OUTPUT_DIR"
du -sh "$OUTPUT_DIR"
