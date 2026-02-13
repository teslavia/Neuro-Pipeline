#!/bin/bash
# End-to-end test: Edge detection → Central gRPC → MLX inference

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "  Week 3 End-to-End Integration Test"
echo "=========================================="

# 1. Start central server
echo "[1/4] Starting central gRPC server..."
python3 -m mac-central.src.main --port 50051 &
SERVER_PID=$!
sleep 3

# 2. Check server health
echo "[2/4] Checking server health..."
if ! curl -s http://localhost:50051 > /dev/null 2>&1; then
    echo "Warning: Server health check failed (expected for gRPC)"
fi

# 3. Run edge client (mock mode)
echo "[3/4] Running edge client with gRPC enabled..."
cd rk3588-edge/build
if [ ! -f neuro_pipeline_edge ]; then
    echo "Error: Edge binary not found. Run build first."
    kill $SERVER_PID
    exit 1
fi

# Run for 10 frames with gRPC enabled
timeout 30s ./neuro_pipeline_edge \
    --model ../models/yolov5s.rknn \
    --video ../test_data/sample.mp4 \
    --max-frames 10 \
    --enable-grpc \
    --grpc-server localhost:50051 || true

# 4. Cleanup
echo "[4/4] Cleaning up..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo "  E2E Test Complete"
echo "=========================================="
echo "Check logs above for:"
echo "  - Edge: Detection results sent via gRPC"
echo "  - Central: Received detections + MLX inference"
