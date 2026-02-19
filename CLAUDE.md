# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Neuro-Pipeline is a heterogeneous AI inference system with two halves:
- **RK3588 Edge** (`rk3588-edge/`): C++17 real-time video pipeline using V4L2/MPP/RGA hardware acceleration and RKNN NPU inference. Cross-compiled for ARM64.
- **Mac Central** (`mac-central/`): Python 3.10+ orchestration server using MLX for LLM/VLM inference on Apple Silicon. Receives detections via gRPC, runs semantic analysis, persists to SQLite.
- **Communication**: gRPC + Protobuf (`proto/neuro_pipeline.proto`), optional mTLS.

## Third-Party Dependencies

All external dependencies live under `third_party/` (see `third_party/README.md`):

| Directory | Type | Purpose |
|-----------|------|---------|
| `third_party/rknn-toolkit2/` | git submodule | Rockchip SDK: RKNN/MPP/RGA headers + aarch64 libs |
| `third_party/googletest/` | git submodule (v1.14.0) | C++ unit testing framework |
| `third_party/stubs/` | project code | Minimal type stubs for CI native builds |

```bash
# Initialize submodules after clone
git submodule update --init --depth 1

# Assemble sysroot from submodule (or fallback to local RKSDK)
bash tools/cross_compile_env/prepare_sysroot.sh
```

The sysroot (`tools/cross_compile_env/sysroot/`) is a build artifact assembled by `prepare_sysroot.sh` — it is NOT tracked in git.

## Build & Test Commands

### Justfile (recommended)
```bash
just --list          # Show all commands
just test-py         # All Python tests
just test-py-unit    # Unit tests only
just test-dashboard  # Dashboard tests
just test-cpp        # C++ tests (requires build)
just build-edge      # Build C++ edge (mock HAL)
just test-all        # Python + dashboard + C++
just proto           # Regenerate protobuf
just monitoring-up   # Start Prometheus + Grafana
```

### Protobuf Generation (required after proto changes)
```bash
python3 tools/generate_proto.py
```

### C++ Edge — Cross-Compile
```bash
# Docker cross-compile (recommended)
USE_MOCK_HAL=ON bash tools/cross_compile_env/build_rk3588.sh   # mock (no hardware)
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh  # real (needs sysroot)

# Native build (mock HAL, for tests — needs googletest submodule)
git submodule update --init --depth 1 third_party/googletest
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
pytest tests/ -v --tb=short

# Single test file
pytest tests/unit_tests/test_grpc_server.py -v

# Single test
pytest tests/unit_tests/test_grpc_server.py::test_health_check -v

# Dashboard + E2E + chaos tests (from repo root)
pytest extensions/dashboard/tests/ tests/e2e/ tests/chaos/ -v
```

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

v2.3: `DetectionQueue` (`src/communication/detection_queue.cpp`) buffers detections during gRPC disconnects; auto-drains on reconnect.

v2.4: JPEG frame encoding via `stb_image_write` — `pipeline_coordinator.cpp` encodes RGA output (RGB888 640×640) to JPEG and sets `frame_data` on gRPC `DetectionResult`. Controlled by `edge.send_frame_data` (default off) and `edge.jpeg_quality` (default 70). Files: `src/utils/jpeg_encoder.hpp`, `src/utils/stb_image_write_impl.cpp`, `third_party/stb_image_write.h`.

v2.4.1: `InputSource` Strategy pattern (`include/neuro/hal/input_source.hpp`) replaces 18-branch switch with polymorphism. `InputSourceFactory` creates V4L2/RTSP/File sources. Config struct split into 4 sub-structs (`pipeline_config.hpp`).

### Central Server (Python, async)
```
gRPC Server → DetectionProcessor → [SQLite Store, VLM Pipeline, Alert Manager, Metrics]
                     ↓ EventBus                    ↓
               ServiceContainer          MLX Inference Engine (LLM or VLM mode)
```
Entry point: `mac-central/src/main.py`. Config: `config.yaml` (root).

Key subsystems:
- `src/core/container.py` — DI container with lazy subsystem initialization (v2.4.1)
- `src/core/config_loader.py` — Generic dataclass config loader (v2.4.1)
- `src/core/logging.py` — Unified logger factory (v2.4.1)
- `src/core/event_bus.py` — EventBus for decoupled event dispatch (v2.4.1)
- `src/core/error_handling.py` — `@safe_async` decorator (v2.4.1)
- `src/communication/grpc_server.py` — gRPC server with rate limiting and input validation
- `src/communication/model_actions.py` — ModelActionHandler Strategy pattern (v2.4.1)
- `src/pipeline/detection_processor.py` — Detection processing (extracted from orchestrator, v2.4.1)
- `src/pipeline/vlm_pipeline.py` — VLM processing pipeline (extracted from orchestrator, v2.4.1)
- `src/application_logic/central_orchestrator.py` — Slim orchestrator (503→120 lines, v2.4.1)
- `src/llm_vlm/mlx_llm_inference.py` — dual-mode MLX engine (LLM text / VLM multimodal), runtime model switching
- `src/storage/detection_store.py` — SQLite Facade with 3 internal repos (v2.4.1)
- `src/observability/` — Prometheus metrics, circuit breaker, alerting with severity routing, OTel tracing
- `src/core/hot_reload.py` — Config file watcher with debounced change detection (v2.3)
- `src/model_management/vlm_validator.py` — VLM model validation pipeline with benchmarks (v2.3)

### Dashboard
`extensions/dashboard/app.py` — FastAPI + htmx + WebSocket. HTTP Basic Auth (env vars `DASHBOARD_USER`/`DASHBOARD_PASS`).

v2.4.1: FastAPI DI via `extensions/dashboard/services/deps.py` — eliminates 14 global variables.

v2.3 endpoints:
- `GET/PUT /api/v2/logging/level` — dynamic log level
- `PUT /api/v2/config` — triggers hot-reload via `ConfigWatcher.force_reload()`

### Monitoring (v2.3)
- Prometheus alert rules: `infra/prometheus/rules/neuro-pipeline.rules.yml`
- SLO dashboard: `infra/grafana/dashboards/slo-dashboard.json`
- Grafana alerting: `infra/grafana/provisioning/alerting.yml`

## Key Conventions

- **Async fixtures**: Use `@pytest_asyncio.fixture`, not `@pytest.fixture` (pytest-asyncio strict mode).
- **pytest skip in fixtures**: Use `pytest.skip()` inside the fixture body, not `@pytest.mark.skipif` on the fixture (pytest 9.x breaks on decorated fixtures).
- **Structlog vs logging**: `grpc_server.py` and some modules use `structlog` when available, falling back to `logging`. Tests should mock `logger` directly rather than using `caplog`.
- **Cross-compile gotchas**: Don't set `CMAKE_SYSROOT` (partial sysroot breaks libc). Run `dot_clean .` before Docker builds on macOS. MPP `.so` symlinks break on macOS git — use `.so.0` files. Sysroot is a build artifact — run `prepare_sysroot.sh` before Docker build.
- **Submodule gotchas**: macOS `git submodule` clone may emit `non-monotonic index` warnings from `._` files — harmless. CI `test-cpp` only inits googletest submodule (avoids cloning large rknn-toolkit2).
- **Version bumps** touch: `VERSION.json`, `constants.hpp` (`kEdgeVersion`), `grpc_server.py`, `main.py`, and all tests that assert version strings.
- **Dashboard tests** need `conftest.py` to add repo root to `sys.path` (extensions/ is outside mac-central/).
- **common::Buffer** is abstract — use `BufferFactory::CreateDMABuffer()` for concrete instances.
- **RGA `wrapbuffer_fd`** is a macro — use `wrapbuffer_fd_t()` in C++ code.
- **stb_image_write**: Header-only JPEG encoder (`third_party/stb_image_write.h`). Implementation compiled in `src/utils/stb_image_write_impl.cpp` (defines `STB_IMAGE_WRITE_IMPLEMENTATION` once). Wrapper: `src/utils/jpeg_encoder.hpp`.

## Release Process

1. Complete work on `dev` branch with version bump commit
2. `git checkout -b milestone/<name>` from dev
3. `git checkout main && git merge dev`
4. `git tag -a vX.Y.Z -m "short description"` on main
5. Push branches and tag as needed
6. `git checkout dev` to continue

## Config

`config.yaml` at repo root is the unified config. Key sections: `edge`, `central`, `tls`, `storage`, `vlm_rules`, `alerting` (with `routes` and `rules`), `rate_limiting`, `sessions`, `cloud_storage`, `tracing`, `batch`.

v2.3 additions:
- `edge.cache_queue` — offline detection buffer (max_entries, max_memory_mb)
- `central.vlm_models` — multiple VLM model variants for runtime switching
- Hot-reloadable sections (no restart): `logging.level`, `vlm_rules`, `alerting.rules`, `rate_limiting`
- Non-hot-reloadable (needs restart): `central.host/port`, `tls.*`, `storage.*`, `central.model_path`

v2.4 additions:
- `edge.send_frame_data` — enable JPEG frame encoding in gRPC DetectionResult (default `false`)
- `edge.jpeg_quality` — JPEG quality 1-100 (default 70, ~30-50KB per 640×640 frame)

## Devcontainer

`.devcontainer/` provides a ready-to-use development environment. Run `just --list` after container creation.
