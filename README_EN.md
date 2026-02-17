<h1 align="center">Neuro-Pipeline</h1>

<p align="center">
  <b>heterogeneous AI inference — RK3588 NPU edge + Apple Silicon central</b>
</p>

<p align="center">
  <a href="https://github.com/teslavia/Neuro-Pipeline/actions"><img src="https://github.com/teslavia/Neuro-Pipeline/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-2.0.0-green.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-522+-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/C%2B%2B-17-00599C.svg?logo=cplusplus&logoColor=white" alt="C++17">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white" alt="Python">
</p>

<p align="center">
  <a href="README.md">中文</a> | <b>English</b>
</p>

---

```
Camera --> V4L2 --> MPP --> RGA --> RKNN NPU --> gRPC --> MLX VLM --> Alert
           capture  decode  resize  YOLO detect  stream   analyze    action
           |<--- zero-copy DMA-BUF --->|         |<- mTLS ->|
```

## Highlights

| | Edge (RK3588) | Central (Mac Mini) |
|---|---|---|
| **Hardware** | 6 TOPS NPU, 8-core ARM | Apple Silicon UMA |
| **AI Model** | YOLOv5/v8 INT8 (8–21 MB) | Llama-3.2-3B 4-bit (1.7 GB) |
| **Framework** | RKNN SDK 2.0 / 3-Core | MLX + mlx-vlm |
| **Language** | C++17 / CMake | Python 3.10+ / asyncio |
| **Latency** | 20.3ms inference | 326ms–1.9s VLM |
| **Throughput** | 28.5 FPS @ 1080p (Adaptive) | ~100 tok/s |

**Key capabilities:**
- **Zero-copy DMA-BUF pipeline** — V4L2 → MPP → RGA → RKNN, no CPU memcpy
- **Multi-model hot switching** — YOLOv5s/v5m/v8s dynamic switching, NPU 3-core independent loading
- **Temporal Tracking + Behavior Analysis** — IoU matching, auto-detection of loitering/running/staying
- **Adaptive Frame Rate** — Dynamic 5–30 FPS based on density, power saving when idle
- **Event-driven upload** — 96% bandwidth savings, only critical detections sent
- **Dual-mode VLM** — Text-only LLM or multimodal (Qwen2-VL)
- **Reasoning Chain + RAG** — 3-step reasoning (observe -> reason -> verify) + history retrieval
- **Model Lifecycle Management** — Deploy/Uninstall/Rollback/A-B Test, gRPC ManageModel RPC
- **Time-series Analytics Engine** — Metrics write/query/aggregate (FPS/Latency/Count)
- **Anomaly Baseline** — Z-score detection, auto-learning history baseline
- **mTLS gRPC** — Bidirectional streaming with mutual TLS authentication
- **RTSP Source** — Network camera support (RTSP over TCP/UDP)
- **Video Recording** — Event-triggered recording with ring buffer pre-record
- **Observability** — Prometheus metrics, health probes, circuit breaker, alerting
- **SQLite persistence** — Detection history survives restarts, atomic backup, 7-day retention
- **Web dashboard** — FastAPI + htmx + WebSocket real-time monitoring, HTTP Basic Auth
- **Security hardening** — gRPC rate limiting, protobuf input validation, audit logging

## Architecture

```
+------------------------------+                         +------------------------------+
|      RK3588 Edge Device      |    gRPC / mTLS / PB     |      Mac Mini Central        |
|      Embedded Linux / C++    | <=====================> |    macOS / Python / MLX       |
|                              |  detections, frames,    |                              |
|  +------------------------+  |  commands, VLM results  |  +------------------------+  |
|  | L5  Pipeline Coord     |  |                         |  | L5  Orchestrator       |  |
|  | L4  gRPC Client        |  |                         |  | L4  gRPC Server        |  |
|  | L3  RKNN NPU + YOLO    |  |                         |  | L3  MLX LLM / VLM      |  |
|  | L2  Zero-Copy Buffers  |  |                         |  | L2  SQLite + Metrics   |  |
|  | L1  V4L2 / MPP / RGA   |  |                         |  | L1  Apple Silicon UMA  |  |
|  +------------------------+  |                         |  +------------------------+  |
+------------------------------+                         +------------------------------+
                                                                      |
                                                            +---------+---------+
                                                            |     Dashboard     |
                                                            |  FastAPI + htmx   |
                                                            +-------------------+
```

**Zero-copy data flow (RK3588):**

```
V4L2 Camera --> MPP Decoder --> RGA Processor --> RKNN NPU
     |               |               |               |
     +---------------+---------------+---------------+
              DMA-BUF fd passing (zero memory copy)
```

## Performance

```
Edge Pipeline Breakdown                 End-to-End (Detection + VLM)
-------------------------               ----------------------------
V4L2 capture     3.2 ms                 Edge capture      3.2 ms
MPP decode       2.1 ms  (hardware)     Edge inference   20.3 ms
RGA resize       1.5 ms  (hardware)     gRPC transport    5.0 ms
RKNN inference  20.3 ms  (NPU)          Central VLM     976.0 ms
YOLO postproc    2.8 ms  (CPU)          Response          5.0 ms
gRPC send        5.2 ms                 -------------------------
-------------------------               Total          ~1,010 ms
Total           35.1 ms  (~28.5 FPS)
```

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Edge inference latency | < 30ms | 20.3ms | ✅ |
| Video frame rate | ≥ 25 FPS | 28.5 FPS | ✅ |
| NPU utilization | > 60% | 72% | ✅ |
| Edge memory (RSS) | < 512MB | ~280MB | ✅ |
| Central VLM throughput | — | ~100 tok/s | ✅ |
| MLX model load | < 3s | 755ms | ✅ |

### Multi-model Comparison (RK3588 NPU Core 0, 1080p → 640×640)

| Model | Frames/30s | Detections | Person Avg Conf | Person Range | Other Classes |
|-------|------------|------------|-----------------|--------------|---------------|
| YOLOv5s (8.5 MB) | 57 | 65 | 71.6% | 51.0–78.9% | book |
| YOLOv5m (21 MB) | 23 | 24 | 90.6% | 89.2–92.7% | bed |
| YOLOv8s (13 MB) | 26 | 26 | 85.0% | 83.2–87.4% | bed, tie, toothbrush |

## Quick Start

### Edge — Cross-compile for RK3588

```bash
# Initialize third-party dependencies (first time after clone)
git submodule update --init --depth 1

# Prepare sysroot (extract headers + libs from submodule or local RKSDK)
bash tools/cross_compile_env/prepare_sysroot.sh

# Docker cross-compile (recommended)
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh

# Deploy + run on device
bash tools/deploy_and_run.sh
```

### Central — Mac Mini setup

```bash
cd mac-central
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Generate protobuf bindings
python3 tools/generate_proto.py

# Start server
python -m src.main --config ../config.yaml
```

### Dashboard

```bash
cd extensions/dashboard
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
# → http://localhost:8080
```

## Project Structure

```
neuro-pipeline/
├── rk3588-edge/                   # Edge device (C++17)
│   ├── src/
│   │   ├── hal/                   #   V4L2, MPP, RGA, DRM, RTSP (real + mock)
│   │   ├── ai_inference/          #   RKNN, YOLOv5/v8, Multi-model mgmt/scheduling
│   │   ├── data_processing/       #   Zero-copy buffers, pool, temporal tracking, detection cache
│   │   ├── communication/         #   gRPC client (streaming + bidi)
│   │   └── app/                   #   Pipeline coordinator, adaptive FPS, recorder
│   ├── tests/                     #   GoogleTest (211 tests)
│   └── cmake/                     #   aarch64 toolchain
├── mac-central/                   # Central server (Python)
│   ├── src/
│   │   ├── communication/         #   gRPC async server, rate limiter
│   │   ├── llm_vlm/               #   MLX LLM/VLM, reasoning chain, RAG retrieval
│   │   ├── application_logic/     #   Orchestrator, behavior analysis, anomaly baseline
│   │   ├── model_management/      #   Model registry, A/B testing
│   │   ├── analytics/             #   Time-series engine, auto-labeling, ReID
│   │   ├── reporting/             #   Report generator
│   │   ├── storage/               #   SQLite persistence, cloud storage
│   │   └── observability/         #   Metrics, tracing, alerting
│   └── tests/                     #   pytest (311 tests: 250 unit + 61 e2e/chaos)
├── proto/                         # Protobuf service definitions
├── extensions/
│   ├── dashboard/                 # FastAPI + htmx monitoring UI
│   └── monitoring/                # Grafana + Prometheus stack
├── third_party/
│   ├── rknn-toolkit2/             # git submodule (RKNN SDK + MPP/RGA)
│   ├── googletest/                # git submodule (v1.14.0)
│   └── stubs/                     # Minimal stub headers for CI builds
├── tools/
│   ├── cross_compile_env/         #   Docker aarch64 toolchain + sysroot (build artifact)
│   ├── certs/                     #   mTLS certificate generation
│   └── services/                  #   systemd + launchd configs
├── config.yaml                    # Unified configuration
└── VERSION.json                   # v1.3.0
```

## Test Coverage

| Component | Framework | Tests | Notes |
|-----------|-----------|-------|-------|
| C++ Edge (Mock HAL) | GoogleTest | 211 | Buffer, pool, HAL, YOLOv5/v8, multi-model, tracker, adaptive FPS |
| Python Central | pytest | 311 | Rate limiting, health, circuit breaker, input validation, metrics, tracing, behavior, RAG |
| Total | — | 522+ | Cross-compile mock ON/OFF both pass |

## Technology Stack

| | RK3588 Edge | Mac Mini Central |
|---|---|---|
| Language | C++17 | Python 3.10+ |
| Build | CMake 3.20+ | pip / setuptools |
| Video | V4L2 + MPP (HW decode) | — |
| Image | RGA (HW resize/convert) | Pillow |
| AI | RKNN NPU (6 TOPS) | MLX (Apple Silicon) |
| Model | .rknn INT8 quantized | MLX 4-bit quantized |
| Comm | gRPC C++ | gRPC Python (asyncio) |
| Metrics | — | Prometheus + /metrics |
| Storage | — | SQLite (WAL mode) |
| Testing | GoogleTest | pytest |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | 5-layer design, zero-copy pipeline, data flow |
| [API Reference](docs/API_REFERENCE.md) | gRPC services, REST endpoints, HAL APIs |
| [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) | Cross-compile, device deploy, mTLS, services |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [Technical Decisions](docs/TECHNICAL_DECISIONS.md) | 24 architecture decision records (TD-001 ~ TD-024) |
| [KPI Report](docs/performance/kpi-report.md) | Benchmark results and pipeline breakdown |

## Milestones

| Version | Milestone | Key Deliverables |
|---------|-----------|-----------------|
| v0.1.0 | Foundation | CMake, Docker toolchain, 8 modules, 101 tests |
| v0.2.0 | HAL + AI | Real V4L2/MPP/RGA/RKNN, 28.5 FPS, zero-copy |
| v0.3.0 | gRPC + MLX | Bidirectional streaming, MLX stub engine |
| v0.4.0 | Hardening | 4-bit quantization, dashboard, config-driven VLM |
| v0.5.0 | Production | mTLS, SQLite, VLM multimodal, async queue |
| v1.0.0 | Observability | Prometheus, health probes, circuit breaker, alerting |
| v1.1.0 | Scale + Multi-edge | Multi-camera, multi-device, VLM batch, Grafana, chaos tests |
| v1.2.0 | Production Hardening | Exception hierarchy, config validation, graceful shutdown, RTSP, video recording |
| v1.3.0 | Security + Activation | Rate limiting, input validation, dashboard auth, audit logging, dead code activation |
| v2.0.0 | Intelligence | Multi-model hot switching (YOLOv5/v8), NPU 3-core scheduling, Temporal Tracking v2, Dynamic config |

## License

[MIT License](LICENSE) — Copyright (c) 2026 Teslavia
