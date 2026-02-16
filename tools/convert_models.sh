#!/usr/bin/env bash
# tools/convert_models.sh — Download and convert YOLOv5m + YOLOv8s to RKNN (INT8)
#
# Usage:
#   bash tools/convert_models.sh [--output-dir DIR]
#
# Prerequisites:
#   - rknn-toolkit2 Python environment, OR
#   - RKSDK model zoo at /Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-$REPO_DIR/models}"
RKSDK_DIR="${RKSDK_DIR:-/Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK}"
RKNN_ZOO="$RKSDK_DIR/rknn_model_zoo"
TARGET_PLATFORM="rk3588"

mkdir -p "$OUTPUT_DIR"

# Airockchip optimized ONNX models (pre-quantization friendly)
YOLOV5M_ONNX_URL="https://ftp.space.rockchip.com/rknn/rknn-toolkit2/models/CV/object_detection/yolo/yolov5m_relu_tk2_RK3588_i8.onnx"
YOLOV8S_ONNX_URL="https://ftp.space.rockchip.com/rknn/rknn-toolkit2/models/CV/object_detection/yolo/yolov8s_tk2_RK3588_i8.onnx"

echo "=== YOLOv5m + YOLOv8s → RKNN Conversion ==="
echo "Output: $OUTPUT_DIR"
echo ""

# --- Download ONNX models ---
download_if_missing() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    echo "[skip] Already exists: $dest"
  else
    echo "[download] $url"
    wget -q --show-progress -O "$dest" "$url" || {
      echo "[warn] wget failed, trying curl..."
      curl -L -o "$dest" "$url"
    }
  fi
}

download_if_missing "$YOLOV5M_ONNX_URL" "$OUTPUT_DIR/yolov5m.onnx"
download_if_missing "$YOLOV8S_ONNX_URL" "$OUTPUT_DIR/yolov8s.onnx"

# --- Convert to RKNN ---
convert_model() {
  local onnx="$1" output="$2" model_type="$3"

  if [[ -f "$output" ]]; then
    echo "[skip] Already exists: $output"
    return 0
  fi

  echo "[convert] $onnx → $output"

  # Method 1: Use our convert_onnx_to_rknn.py
  if python3 -c "import rknn" 2>/dev/null; then
    python3 "$SCRIPT_DIR/rknn_toolkit_scripts/convert_onnx_to_rknn.py" \
      --onnx "$onnx" \
      --output "$output" \
      --target-platform "$TARGET_PLATFORM" \
      --quantize
    return $?
  fi

  # Method 2: Use RKSDK model zoo convert.py
  if [[ -d "$RKNN_ZOO/examples/$model_type/python" ]]; then
    echo "[info] Using RKSDK model zoo converter"
    cd "$RKNN_ZOO/examples/$model_type/python"
    python3 convert.py "$onnx" "$TARGET_PLATFORM" i8 "$output"
    return $?
  fi

  echo "[error] No conversion tool available. Install rknn-toolkit2 or set RKSDK_DIR."
  return 1
}

convert_model "$OUTPUT_DIR/yolov5m.onnx" "$OUTPUT_DIR/yolov5m-640-640.rknn" "yolov5"
convert_model "$OUTPUT_DIR/yolov8s.onnx" "$OUTPUT_DIR/yolov8s-640-640.rknn" "yolov8"

echo ""
echo "=== Conversion Complete ==="
ls -lh "$OUTPUT_DIR"/*.rknn 2>/dev/null || echo "(no .rknn files found)"
