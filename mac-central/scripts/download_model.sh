#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$REPO_ROOT/models"
MODEL_NAME="Llama-3.2-3B-Instruct"
HF_REPO="mlx-community/$MODEL_NAME"

echo "=========================================="
echo "  MLX Model Downloader"
echo "=========================================="
echo "Model: $HF_REPO"
echo "Target: $MODEL_DIR/$MODEL_NAME"
echo ""

if ! command -v huggingface-cli &> /dev/null; then
    echo "[ERROR] huggingface-cli not found"
    echo "Install: pip install huggingface-hub"
    exit 1
fi

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

echo "[1/2] Downloading model..."
huggingface-cli download "$HF_REPO" --local-dir "$MODEL_NAME"

echo "[2/2] Verifying model files..."
if [ ! -f "$MODEL_NAME/config.json" ]; then
    echo "[ERROR] Model download incomplete"
    exit 1
fi

echo ""
echo "=========================================="
echo "  Download Complete"
echo "=========================================="
echo "Model path: $MODEL_DIR/$MODEL_NAME"
echo "Size: $(du -sh "$MODEL_NAME" | cut -f1)"
