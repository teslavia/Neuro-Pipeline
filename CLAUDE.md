# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Neuro-Pipeline is a heterogeneous AI inference system with two halves:
- **RK3588 Edge** (`rk3588-edge/`): C++17 real-time video pipeline using V4L2/MPP/RGA hardware acceleration and RKNN NPU inference. Cross-compiled for ARM64.
- **Mac Central** (`mac-central/`): Python 3.10+ orchestration server using MLX for LLM/VLM inference on Apple Silicon. Receives detections via gRPC, runs semantic analysis, persists to SQLite.
- **Communication**: gRPC + Protobuf (`proto/neuro_pipeline.proto`), optional mTLS.

## Build & Test Commands

### Protobuf Generation (required after proto changes)
```bash
python3 tools/generate_proto.py
```

### C++ Edge — Cross-Compile
```bash
# Docker cross-compile (recommended)
USE_MOCK_HAL=ON bash tools/cross_compile_env/build_rk3588.sh   # mock (no hardware)
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh  # real (needs sysroot)

# Native build (mock HAL, for tests)
cd rk3588-edge && mkdir -p build && cd build
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON
make -j$(nproc)
ctest --output-on-failure
```

### Python Central — Tests
```bash
cd mac-central
source .venv/bin/activate  # venv lives at mac-central/.venv

# All unit + integration tests
pytest tests/ -v --tb=short -o "addopts="

# Single test file
pytest tests/unit_tests/test_grpc_server.py -v -o "addopts="

# Single test
pytest tests/unit_tests/test_grpc_server.py::test_health_check -v -o "addopts="

# Dashboard + E2E + chaos tests (from repo root)
pytest extensions/dashboard/tests/ tests/e2e/ tests/chaos/ -v -o "addopts="
```

The `-o "addopts="` override is required — `pyproject.toml` sets coverage flags that break targeted test runs.

### C++ Single Test
```bash
cd rk3588-edge/build
./run_unit_tests --gtest_filter=MemoryPoolTest.AllocSuccess
```

## Architecture

### Edge Pipeline (C++, zero-copy)
```
V4L2 Camera → MPP Decoder → RGA Processor → RKNN NPU → gRPC Client → Central
              (DMA-BUF fd passing, no CPU memcpy between stages)
```
Layers: HAL (`src/hal/`) → Data Processing (`src/data_processing/`) → AI Inference (`src/ai_inference/`) → Communication (`src/communication/`) → App (`src/app/pipeline_coordinator.cpp`).

All HAL modules have real + mock implementations, toggled by `USE_MOCK_HAL` at compile time.

### Central Server (Python, async)
```
gRPC Server → Orchestrator → [SQLite Store, VLM Queue, Alert Manager, Metrics]
                                    ↓
                              MLX Inference Engine (LLM or VLM mode)
```
Entry point: `mac-central/src/main.py`. Config: `config.yaml` (root).

Key subsystems:
- `src/communication/grpc_server.py` — gRPC server with rate limiting and input validation
- `src/application_logic/central_orchestrator.py` — core detection processing, VLM queue, event dispatch
- `src/llm_vlm/mlx_llm_inference.py` — dual-mode MLX engine (LLM text / VLM multimodal)
- `src/storage/detection_store.py` — SQLite persistence with retry and backup
- `src/observability/` — Prometheus metrics, circuit breaker, alerting with severity routing, OTel tracing

### Dashboard
`extensions/dashboard/app.py` — FastAPI + htmx + WebSocket. HTTP Basic Auth (env vars `DASHBOARD_USER`/`DASHBOARD_PASS`).

## Key Conventions

- **Async fixtures**: Use `@pytest_asyncio.fixture`, not `@pytest.fixture` (pytest-asyncio strict mode).
- **pytest skip in fixtures**: Use `pytest.skip()` inside the fixture body, not `@pytest.mark.skipif` on the fixture (pytest 9.x breaks on decorated fixtures).
- **Structlog vs logging**: `grpc_server.py` and some modules use `structlog` when available, falling back to `logging`. Tests should mock `logger` directly rather than using `caplog`.
- **Cross-compile gotchas**: Don't set `CMAKE_SYSROOT` (partial sysroot breaks libc). Run `dot_clean .` before Docker builds on macOS. MPP `.so` symlinks break on macOS git — use `.so.0` files.
- **Version bumps** touch: `VERSION.json`, `constants.hpp` (`kEdgeVersion`), `grpc_server.py`, `main.py`, and all tests that assert version strings.
- **Dashboard tests** need `conftest.py` to add repo root to `sys.path` (extensions/ is outside mac-central/).
- **common::Buffer** is abstract — use `BufferFactory::CreateDMABuffer()` for concrete instances.
- **RGA `wrapbuffer_fd`** is a macro — use `wrapbuffer_fd_t()` in C++ code.

## Release Process

1. Complete work on `dev` branch with version bump commit
2. `git checkout -b milestone/<name>` from dev
3. `git checkout main && git merge dev`
4. `git tag -a vX.Y.Z -m "short description"` on main
5. Push branches and tag as needed
6. `git checkout dev` to continue

## Config

`config.yaml` at repo root is the unified config. Key sections: `edge`, `central`, `tls`, `storage`, `vlm_rules`, `alerting` (with `routes` and `rules`), `rate_limiting`, `sessions`, `cloud_storage`, `tracing`, `batch`.
