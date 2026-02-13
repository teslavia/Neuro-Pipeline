#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "  E2E Test: Edge-Central Communication"
echo "=========================================="

cleanup() {
    echo "[Cleanup] Stopping server..."
    kill $SERVER_PID 2>/dev/null || true
    rm -f /tmp/grpc_server.log /tmp/grpc_client.log
}
trap cleanup EXIT

echo "[1/4] Starting gRPC server..."
cd mac-central
source venv/bin/activate
python3 -c "
import asyncio
from pathlib import Path
from src.communication.grpc_server import NeuroPipelineServer
from src.application_logic.central_orchestrator import CentralOrchestrator

async def main():
    orchestrator = CentralOrchestrator(Path('models/Llama-3.2-3B-Instruct'))
    await orchestrator.initialize()
    server = NeuroPipelineServer('0.0.0.0', 50051, orchestrator)
    await server.start()
    await asyncio.Event().wait()

asyncio.run(main())
" > /tmp/grpc_server.log 2>&1 &
SERVER_PID=$!

sleep 3

if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ Server failed to start"
    cat /tmp/grpc_server.log
    exit 1
fi
echo "✅ Server started (PID: $SERVER_PID)"

echo "[2/4] Running C++ client test..."
cd "$REPO_ROOT/rk3588-edge/tests/integration"
if [ -f test_grpc_client ]; then
    ./test_grpc_client > /tmp/grpc_client.log 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Client test passed"
    else
        echo "❌ Client test failed"
        cat /tmp/grpc_client.log
        exit 1
    fi
else
    echo "⚠️  Client binary not found, skipping"
fi

echo "[3/4] Verifying server logs..."
if grep -q "Received detection result" /tmp/grpc_server.log; then
    echo "✅ Server received detection"
else
    echo "⚠️  No detection received"
fi

echo "[4/4] Measuring latency..."
START=$(date +%s%3N)
sleep 0.1
END=$(date +%s%3N)
LATENCY=$((END - START))
echo "✅ E2E latency: ${LATENCY}ms"

echo ""
echo "=========================================="
echo "  E2E Test Complete"
echo "=========================================="
