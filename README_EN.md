<h1 align="center">Neuro-Pipeline</h1>

<p align="center">
  <b>heterogeneous AI inference — RK3588 NPU edge + Apple Silicon central</b>
</p>

<p align="center">
  <a href="https://github.com/teslavia/Neuro-Pipeline/actions"><img src="https://github.com/teslavia/Neuro-Pipeline/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-1.3.0-green.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-250_Python-brightgreen.svg" alt="Tests">
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
| **AI Model** | YOLOv5 INT8 (8.5 MB) | Llama-3.2-3B 4-bit (1.7 GB) |
| **Framework** | RKNN SDK 2.0 | MLX + mlx-vlm |
| **Language** | C++17 / CMake | Python 3.10+ / asyncio |
| **Latency** | 20.3ms inference | 326ms–1.9s VLM |
| **Throughput** | 28.5 FPS @ 1080p | ~100 tok/s |

**Key capabilities:**
- **Zero-copy DMA-BUF pipeline** — V4L2 → MPP → RGA → RKNN, no CPU memcpy
- **Event-driven upload** — 96% bandwidth savings, only critical detections sent
- **Dual-mode VLM** — text-only LLM or vision-language multimodal (Qwen2-VL)
- **mTLS gRPC** — bidirectional streaming with mutual TLS authentication
- **Observability** — Prometheus metrics, health probes, circuit breaker, alerting
- **SQLite persistence** — detection history survives restarts, atomic backup, 7-day retention
- **Web dashboard** — FastAPI + htmx + WebSocket real-time monitoring, HTTP Basic Auth
- **Multi-camera + Multi-edge** — single central manages multiple devices, parallel inference
- **VLM batch inference** — accumulator with multi-turn conversation context
- **Cloud storage** — S3/MinIO async upload, distributed tracing (OTel)
- **Security hardening** — gRPC rate limiting, protobuf input validation, audit logging
- **RTSP source** — network camera support via RTSP URL
- **Video recording** — event-triggered recording with ring buffer
- **NPU 3-core scheduling** — round-robin core assignment per camera
- **Graceful shutdown** — VLM queue drain + configurable timeout

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
Total           35.1ms  (~28.5 FPS)
```

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Edge inference latency | < 30ms | 20.3ms | ✅ |
| Video frame rate | ≥ 25 FPS | 28.5 FPS | ✅ |
| NPU utilization | > 60% | 72% | ✅ |
| Edge memory (RSS) | < 512MB | ~280MB | ✅ |
| Central VLM throughput | — | ~100 tok/s | ✅ |
| MLX model load | < 3s | 755ms | ✅ |

## Quick Start

### Edge — Cross-compile for RK3588

```bash
# Prepare sysroot (extract headers + libs from RKSDK)
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
│   │   ├── ai_inference/          #   RKNN engine, YOLO postprocessor, NPU scheduler
│   │   ├── data_processing/       #   Zero-copy buffers, memory pool
│   │   ├── communication/         #   gRPC client (streaming + bidi)
│   │   └── app/                   #   Pipeline coordinator, video recorder
│   ├── tests/                     #   GoogleTest (146 tests)
│   └── cmake/                     #   aarch64 toolchain
├── mac-central/                   # Central server (Python)
│   ├── src/
│   │   ├── communication/         #   gRPC async server, rate limiter
│   │   ├── llm_vlm/               #   MLX LLM/VLM dual-mode engine
│   │   ├── application_logic/     #   Orchestrator, circuit breaker
│   │   ├── storage/               #   SQLite persistence, cloud storage
│   │   └── observability/         #   Metrics, tracing, alerting
│   └── tests/                     #   pytest (247 tests: 209 unit + 38 e2e/chaos)
├── proto/                         # Protobuf service definitions
├── extensions/
│   ├── dashboard/                 # FastAPI + htmx monitoring UI
│   └── monitoring/                # Grafana + Prometheus stack
├── tools/
│   ├── cross_compile_env/         #   Docker aarch64 toolchain + sysroot
│   ├── certs/                     #   mTLS certificate generation
│   └── services/                  #   systemd + launchd configs
├── config.yaml                    # Unified configuration
└── VERSION.json                   # v1.3.0
```

## Test Coverage

| Component | Framework | Tests | Notes |
|-----------|-----------|-------|-------|
| C++ Edge (mock HAL) | GoogleTest | 146 | Buffer, pool, thread, HAL, YOLO, gRPC |
| Python Central | pytest | 250 | 212 unit + 38 e2e/chaos (8 skipped) |
| Total | — | 396+ | Cross-compile mock ON/OFF both pass |

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

## License

[MIT License](LICENSE) — Copyright (c) 2026 Teslavia
