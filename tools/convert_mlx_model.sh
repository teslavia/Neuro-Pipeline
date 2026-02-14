#!/usr/bin/env bash
# Convert HuggingFace model to MLX native format with 4-bit quantization.
# Usage: bash tools/convert_mlx_model.sh [input_dir] [output_dir]
#
# Requires: pip install mlx-lm
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INPUT_DIR="${1:-$REPO_ROOT/mac-central/models/Llama-3.2-3B-Instruct}"
OUTPUT_DIR="${2:-$REPO_ROOT/mac-central/models/Llama-3.2-3B-Instruct-4bit-mlx}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "ERROR: Input model directory not found: $INPUT_DIR"
    exit 1
fi

echo "=== MLX Model Conversion ==="
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_DIR"
echo "Quantization: 4-bit"
echo ""

# Check mlx_lm is installed
if ! python3 -c "import mlx_lm" 2>/dev/null; then
    echo "ERROR: mlx_lm not installed. Run: pip install mlx-lm"
    exit 1
fi

# Convert with 4-bit quantization
python3 -m mlx_lm.convert \
    --hf-path "$INPUT_DIR" \
    --mlx-path "$OUTPUT_DIR" \
    -q \
    --q-bits 4

echo ""
echo "=== Conversion Complete ==="
echo "Output: $OUTPUT_DIR"
du -sh "$OUTPUT_DIR"
echo ""
echo "To verify: python3 -c \"from mlx_lm import load, generate; m, t = load('$OUTPUT_DIR'); print(generate(m, t, prompt='Hello', max_tokens=20))\""
