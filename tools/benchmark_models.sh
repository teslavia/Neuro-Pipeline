#!/usr/bin/env bash
# tools/benchmark_models.sh — Compare YOLOv5s / YOLOv5m / YOLOv8s on RK3588
#
# Usage:
#   bash tools/benchmark_models.sh [--host HOST] [--duration SECS]
#
# Requires: grpcurl (or python grpc client), ssh access to edge device
set -euo pipefail

EDGE_HOST="${1:-192.168.1.70}"
GRPC_SERVER="${2:-localhost:50051}"  # Central server (Mac Mini)
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
  local gen_path
  gen_path="$(cd "$(dirname "$0")/../mac-central/src/generated" 2>/dev/null && pwd)"
  python3 -c "
import grpc, sys
sys.path.insert(0, '$gen_path')
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
    print('  Switched to $model_id')
except Exception as e:
    print(f'  Switch failed: {e}')
channel.close()
" 2>/dev/null || echo "  [warn] gRPC switch failed"
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

  # Sample NPU load periodically
  ssh "rock@$EDGE_HOST" \
    "for i in \$(seq 1 $((DURATION/5))); do cat /sys/kernel/debug/rknpu/load 2>/dev/null; sleep 5; done" \
    > "$LOG_DIR/${model_id}_npu.log" 2>&1 &
  local npu_pid=$!

  sleep "$DURATION"
  kill "$pid" "$npu_pid" 2>/dev/null || true
  wait "$pid" "$npu_pid" 2>/dev/null || true

  # Parse metrics from edge logs
  local detections avg_conf avg_latency
  detections=$(grep -c "detections" "$log_file" 2>/dev/null || echo 0)
  avg_conf=$(grep -Eo 'confidence[=:][[:space:]]*[0-9.]+' "$log_file" 2>/dev/null | \
    grep -Eo '[0-9.]+$' | \
    awk '{s+=$1; n++} END {if(n>0) printf "%.1f", s/n*100; else print "N/A"}')
  avg_latency=$(grep -Eo 'latency[=:][[:space:]]*[0-9.]+' "$log_file" 2>/dev/null | \
    grep -Eo '[0-9.]+$' | \
    awk '{s+=$1; n++} END {if(n>0) printf "%.1f", s/n; else print "N/A"}')
  local avg_npu
  avg_npu=$(grep -Eo 'Core0:[[:space:]]*[0-9]+' "$LOG_DIR/${model_id}_npu.log" 2>/dev/null | \
    grep -Eo '[0-9]+$' | \
    awk '{s+=$1; n++} END {if(n>0) printf "%.0f", s/n; else print "N/A"}')

  echo "  Detections: $detections | Confidence: ${avg_conf}% | Latency: ${avg_latency}ms | NPU: ${avg_npu}%"
  echo "$model_id,$detections,$avg_conf,$avg_latency,$avg_npu" >> "$LOG_DIR/summary.csv"
}

# Header
echo "model,detections,avg_confidence_pct,avg_latency_ms,avg_npu_pct" > "$LOG_DIR/summary.csv"

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
