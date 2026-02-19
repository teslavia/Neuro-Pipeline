#!/usr/bin/env bash
set -euo pipefail

echo "=== Neuro-Pipeline: post-create setup ==="

# Initialize git submodules
git submodule update --init --depth 1

# Python venv
cd mac-central
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt 2>/dev/null || pip install pytest pytest-asyncio pyyaml httpx fastapi uvicorn prometheus-client
cd ..

# Generate protobuf code
python3 tools/generate_proto.py || echo "Proto generation skipped (may need protoc)"

# Build C++ edge (mock HAL for dev)
cd rk3588-edge
mkdir -p build && cd build
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON 2>/dev/null && make -j$(nproc) 2>/dev/null || echo "C++ build skipped (may need dependencies)"
cd ../..

echo "=== Setup complete. Run 'just --list' to see available commands ==="
