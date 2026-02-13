#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$REPO_ROOT/rk3588-edge/models"
RKSDK="${RKSDK_PATH:-/Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK}"
TARGET_MODEL="$MODEL_DIR/yolov5s-640-640.rknn"

mkdir -p "$MODEL_DIR"

# Check if model already exists
if [ -f "$TARGET_MODEL" ]; then
  echo "✓ Model already exists: $TARGET_MODEL"
  ls -lh "$TARGET_MODEL"
  exit 0
fi

# Search in rknn_model_zoo
if [ -d "$RKSDK/rknn_model_zoo" ]; then
  echo "Searching for YOLO model in $RKSDK/rknn_model_zoo..."
  MODEL=$(find "$RKSDK/rknn_model_zoo" -type f -name "*yolo*640*.rknn" 2>/dev/null | head -1)

  if [ -n "$MODEL" ]; then
    cp "$MODEL" "$TARGET_MODEL"
    echo "✓ Model copied: $(basename "$MODEL")"
    ls -lh "$TARGET_MODEL"
    exit 0
  fi
fi

# Model not found - provide download instructions
echo "⚠ Model not found in RKSDK."
echo ""
echo "Download manually:"
echo "  cd $MODEL_DIR"
echo "  wget https://huggingface.co/airockchip/yolov5/resolve/main/yolov5s_relu.rknn"
echo "  mv yolov5s_relu.rknn yolov5s-640-640.rknn"
echo ""
echo "Or set RKSDK_PATH environment variable:"
echo "  export RKSDK_PATH=/path/to/your/RKSDK"
exit 1
