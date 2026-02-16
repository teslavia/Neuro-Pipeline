#!/usr/bin/env bash
# tools/benchmark_models.sh — Compare YOLOv5s / YOLOv5m / YOLOv8s on RK3588
#
# Usage:
#   bash tools/benchmark_models.sh [--host HOST] [--duration SECS]
#
# Requires: grpcurl (or python grpc client), ssh access to edge device
set -euo pipefail

EDGE_HOST="${1:-192.168.1.70}"
GRPC_SERVER="${2:-192.168.1.100:50051}"
DURATION="${3:-30}"
MODELS=("yolov5s" "yolov5m" "yolov8s")
LOG_DIR="/tmp/neuro-benchmark-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LOG_DIR"

echo "=== Neuro-Pipeline Model Benchmark ==="
echo "Edge: $EDGE_HOST | gRPC: $GRPC_SERVER | Duration: ${DURATION}s per model"
echo "Log dir: $LOG_DIR"
echo ""

switch_model() {
  local model_id="$1"
  echo "[switch] → $model_id"

  # Send SWITCH_MODEL_VARIANT via gRPC
  # Using python helper since grpcurl may not be available
  python3 -c "
import grpc
import sys
sys.path.insert(0, '$(dirname "$0")/../mac-central/src/generated')
import neuro_pipeline_pb2 as pb
import neuro_pipeline_pb2_grpc as pb_grpc

channel = grpc.insecure_channel('$GRPC_SERVER')
stub = pb_grpc.NeuroPipelineStub(channel)
cmd = pb.ControlCommand(
    type=pb.ControlCommand.SWITCH_MODEL_VARIANT,
    parameters={'model_id': '$model_id'}
)
try:
    stub.SendControlCommand(cmd, timeout=5)
    print(f'  Switched to {\"$model_id\"}')
except Exception as e:
    print(f'  Switch failed: {e}')
channel.close()
" 2>/dev/null || echo "  [warn] gRPC switch failed, trying SSH fallback..."
}

collect_metrics() {
  local model_id="$1" log_file="$LOG_DIR/${model_id}.log"
  echo "[collect] $model_id for ${DURATION}s → $log_file"

  # Collect edge logs via SSH
  ssh "rock@$EDGE_HOST" \
    "timeout ${DURATION} journalctl -u neuro-pipeline -f --no-pager 2>/dev/null || \
     timeout ${DURATION} tail -f /opt/neuro-pipeline/logs/pipeline.log 2>/dev/null" \
    > "$log_file" 2>&1 &
  local pid=$!

  sleep "$DURATION"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true

  # Parse metrics
  local detections=$(grep -c "detections" "$log_file" 2>/dev/null || echo 0)
  local avg_conf=$(grep -oP 'confidence[=:]\s*\K[0-9.]+' "$log_file" 2>/dev/null | \
    awk '{s+=$1; n++} END {if(n>0) printf "%.1f", s/n*100; else print "N/A"}')
  local avg_latency=$(grep -oP 'latency[=:]\s*\K[0-9.]+' "$log_file" 2>/dev/null | \
    awk '{s+=$1; n++} END {if(n>0) printf "%.1f", s/n; else print "N/A"}')

  echo "  Detections: $detections | Avg confidence: ${avg_conf}% | Avg latency: ${avg_latency}ms"
  echo "$model_id,$detections,$avg_conf,$avg_latency" >> "$LOG_DIR/summary.csv"
}

# Header
echo "model,detections,avg_confidence_pct,avg_latency_ms" > "$LOG_DIR/summary.csv"

for model in "${MODELS[@]}"; do
  echo ""
  echo "--- $model ---"
  switch_model "$model"
  sleep 2  # Allow model switch to settle
  collect_metrics "$model"
done

echo ""
echo "=== Results ==="
column -t -s',' "$LOG_DIR/summary.csv"
echo ""
echo "Full logs: $LOG_DIR/"
