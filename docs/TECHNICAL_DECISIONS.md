# Technical Decisions Record

**Project**: Neuro-Pipeline
**Version**: v1.3.0
**Last Updated**: 2026-02-16

---

## Decision Log

### TD-001: Zero-Copy Architecture via DMA-BUF

**Date**: 2026-02-11 (Week 1)
**Status**: ✅ Implemented
**Context**: RK3588 边缘设备需要在 V4L2、MPP、RGA、RKNN 之间传输视频帧数据

**Decision**: 使用 DMA-BUF 文件描述符在硬件加速器之间共享物理内存

**Alternatives Considered**:
1. **mmap + memcpy**: 简单但 CPU 开销高（每帧 ~5ms @ 1080p）
2. **Shared memory (SHM)**: 需要额外的同步机制，不支持硬件加速器
3. **DMA-BUF** ✅: 零拷贝，硬件原生支持，Linux 内核标准

**Rationale**:
- 消除 CPU 数据拷贝，节省 ~15ms/frame
- 硬件加速器直接访问物理内存，无需 CPU 介入
- 缓存一致性通过显式 sync 管理（`SyncForDevice/CPU`）

**Trade-offs**:
- ✅ 性能提升 75%（20ms vs 35ms latency）
- ❌ 缓冲区生命周期管理复杂（需要 RAII + refcount）
- ❌ 调试困难（DMA-BUF fd 泄漏不易发现）

**Implementation**: `rk3588-edge/src/hal/drm_allocator.cpp:1-290`

**References**:
- Linux DMA-BUF API: https://www.kernel.org/doc/html/latest/driver-api/dma-buf.html
- Week 2 Retro: `docs/devlog/week2-retro.md:74-95`

---

### TD-002: Event-Driven Communication (Edge → Central)

**Date**: 2026-02-14 (Week 3)
**Status**: ✅ Implemented
**Context**: 边缘侧每秒产生 28.5 帧检测结果，全部上传会消耗 ~50 Mbps 带宽

**Decision**: 边缘侧仅在关键事件触发时上传数据（检测到"人"且置信度 > 0.8）

**Alternatives Considered**:
1. **全量上传**: 简单但带宽消耗高（50 Mbps）
2. **固定采样率** (1 FPS): 可能错过关键事件
3. **事件驱动** ✅: 智能过滤，带宽降至 ~2 Mbps

**Rationale**:
- 减少 96% 的网络流量（50 Mbps → 2 Mbps）
- 中心侧仅处理有价值的数据，降低 MLX 推理负载
- 边缘侧保留完整检测能力（28.5 FPS）

**Trade-offs**:
- ✅ 带宽节省 96%
- ✅ 中心侧推理延迟降低（无需处理空帧）
- ❌ 需要边缘侧实现过滤逻辑（增加 45 行代码）

**Implementation**: `rk3588-edge/src/app/pipeline_coordinator.cpp:178-206`

**References**:
- Week 3 Benchmark: `docs/performance/week3-benchmark.md:50-73`

---

### TD-003: gRPC Client Streaming (非 Bidirectional)

**Date**: 2026-02-14 (Week 3)
**Status**: ✅ Implemented
**Context**: 边缘侧需要向中心侧发送检测结果，中心侧需要返回确认

**Decision**: 使用 gRPC Client Streaming（边缘 → 中心单向流 + 响应）

**Alternatives Considered**:
1. **Unary RPC**: 每次检测一个 RPC 调用，开销高
2. **Bidirectional Streaming**: 支持中心 → 边缘控制指令，但当前不需要
3. **Client Streaming** ✅: 满足当前需求，简单高效

**Rationale**:
- 单向流足够满足当前需求（边缘上报检测结果）
- 避免 Bidirectional 的复杂性（双向流控、死锁风险）
- 未来可扩展为 Bidirectional（Protobuf 接口已预留）

**Trade-offs**:
- ✅ 实现简单（142 行 C++ 客户端）
- ✅ 网络开销低（HTTP/2 多路复用）
- ❌ 中心侧无法主动推送控制指令（需要边缘侧轮询或升级为 Bidirectional）

**Implementation**: `rk3588-edge/src/communication/grpc_client.cpp:99-147`

**Future Work**: Week 4 升级为 Bidirectional Streaming 以支持控制命令

**References**:
- gRPC Streaming Guide: https://grpc.io/docs/what-is-grpc/core-concepts/#server-streaming-rpc
- Protobuf Definition: `proto/neuro_pipeline.proto:13-25`

---

### TD-004: MLX Stub Mode (先实现接口，后集成模型)

**Date**: 2026-02-14 (Week 3)
**Status**: ✅ Implemented (Stub + Real)
**Context**: MLX 模型下载需要 ~6GB 空间和 huggingface-cli，可能阻塞开发

**Decision**: 先实现 MLX 推理引擎的 stub 模式，返回 mock 响应，Week 4 再集成真实模型

**Alternatives Considered**:
1. **直接集成模型**: 阻塞 Week 3 开发（模型下载 + 调试可能需要 2-3 天）
2. **跳过 MLX**: 无法验证端到端通信
3. **Stub Mode** ✅: 解耦开发，先验证通信，后集成模型

**Rationale**:
- 允许 Week 3 并行开发（gRPC 通信 + MLX 接口）
- Stub 模式可验证端到端延迟（270ms，满足 < 500ms 目标）
- 真实模型集成风险隔离到 Week 4

**Trade-offs**:
- ✅ Week 3 按时完成（100% 核心功能）
- ✅ 降低集成风险（模型问题不影响通信验证）
- ❌ 无法测试真实 MLX 推理性能（Week 4 补齐）

**Implementation**: `mac-central/src/llm_vlm/mlx_llm_inference.py:27-50`

**Next Steps**: ✅ Week 4: Llama-3.2-3B-Instruct downloaded, converted to 4-bit MLX, real inference verified (~100 tok/s)

**References**:
- Week 3 Completion: `docs/devlog/WEEK3_COMPLETION_SUMMARY.md:30`
- Model Download Script: `mac-central/scripts/download_model.sh`

---

### TD-005: 交叉编译不设置 CMAKE_SYSROOT

**Date**: 2026-02-11 (Week 1)
**Status**: ✅ Implemented
**Context**: 使用部分 sysroot（仅 RKNN/MPP/RGA 库）进行交叉编译

**Decision**: 不设置 `CMAKE_SYSROOT`，仅通过 `CMAKE_FIND_ROOT_PATH` 指定库路径

**Alternatives Considered**:
1. **完整 sysroot** (2GB+): 包含所有系统库，但体积大、维护困难
2. **CMAKE_SYSROOT + 部分 sysroot**: 导致 libc 头文件路径错误
3. **仅 CMAKE_FIND_ROOT_PATH** ✅: 部分 sysroot 可用，libc 使用工具链自带

**Rationale**:
- 部分 sysroot 仅 37MB（vs 完整 sysroot 2GB+）
- 避免 libc 头文件冲突（工具链自带 vs sysroot）
- 交叉编译速度快（Docker 构建 < 2 分钟）

**Trade-offs**:
- ✅ Sysroot 体积小，易于维护
- ✅ 编译速度快
- ❌ 需要手动管理库依赖（RKNN/MPP/RGA）

**Implementation**: `tools/cross_compile_env/build_rk3588.sh:45-60`

**References**:
- Week 1 Retro: `docs/devlog/week1-retro.md:38-42`
- CMakeLists.txt: `rk3588-edge/CMakeLists.txt:61-85`

---

### TD-006: YOLO 后处理 NCHW 格式

**Date**: 2026-02-13 (Week 2)
**Status**: ✅ Fixed
**Context**: RKNN 输出 tensor 格式为 NCHW（channel-first），初始实现按 NHWC 解析导致 128 个误报

**Decision**: 修正 YOLO 后处理逻辑，按 NCHW 格式解析 tensor

**Root Cause**:
- RKNN SDK 输出格式为 NCHW（与 PyTorch 一致）
- 初始实现错误地按 NHWC（TensorFlow 格式）解析
- 导致置信度和坐标全部错位

**Fix**:
```cpp
// 修复前 (NHWC 错误解析)
float confidence = data[i * num_classes + 4];

// 修复后 (NCHW 正确解析)
int grid_size = grid_h * grid_w;
float confidence = data[4 * grid_size + i];  // channel=4 的所有空间位置
```

**Impact**:
- 误报从 128 个降至 2-3 个有效检测
- 检测框坐标和置信度正确
- FPS 无影响（后处理时间 < 1ms）

**Implementation**: `rk3588-edge/src/ai_inference/yolo_postprocess.cpp:89-120`

**References**:
- Week 2 Retro: `docs/devlog/week2-retro.md:48-73`
- RKNN SDK Docs: RKNN 输出默认为 NCHW 格式

---

### TD-007: DRM Allocator 直接 mmap DMA-BUF fd

**Date**: 2026-02-13 (Week 2)
**Status**: ✅ Fixed
**Context**: 使用 `DRM_IOCTL_MODE_MAP_DUMB` 需要 DRM master 权限，在 render node 上失败

**Decision**: 直接 mmap DMA-BUF fd，无需 MAP_DUMB ioctl

**Root Cause**:
- MAP_DUMB ioctl 仅对 primary node (`/dev/dri/card0`) 有效
- Render node (`/dev/dri/renderD128`) 不支持 legacy DRM ioctls
- 导致 "Permission denied" 错误

**Fix**:
```cpp
// 修复前 (需要 DRM master)
drm_mode_map_dumb map_req = {};
ioctl(drm_fd_, DRM_IOCTL_MODE_MAP_DUMB, &map_req);
mmap(..., map_req.offset);

// 修复后 (直接 mmap DMA-BUF fd)
void* vaddr = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, dma_fd, 0);
```

**Impact**:
- 无需特殊权限，普通用户可运行
- 兼容 render node 和 primary node
- 简化部署流程（无需 sudo 或 DRM master）

**Implementation**: `rk3588-edge/src/hal/drm_allocator.cpp:78-95`

**References**:
- Week 2 Retro: `docs/devlog/week2-retro.md:74-95`
- DRM API: https://www.kernel.org/doc/html/latest/gpu/drm-mm.html

---

## Decision Matrix

| ID | Decision | Status | Week | Impact | Risk |
|----|----------|--------|------|--------|------|
| TD-001 | DMA-BUF Zero-Copy | ✅ | 1 | High (75% perf gain) | Medium (lifecycle mgmt) |
| TD-002 | Event-Driven Comm | ✅ | 3 | High (96% bandwidth save) | Low |
| TD-003 | Client Streaming | ✅ | 3 | Medium | Low (future upgrade) |
| TD-004 | MLX Stub Mode | ✅ | 3 | Medium (decouple dev) | Low |
| TD-005 | No CMAKE_SYSROOT | ✅ | 1 | Medium (build speed) | Low |
| TD-006 | YOLO NCHW Fix | ✅ | 2 | High (fix 128 false pos) | None |
| TD-007 | Direct mmap DMA-BUF | ✅ | 2 | Medium (no sudo) | None |
| TD-008 | Bidirectional Streaming | ✅ | 3.5 | Medium (control commands) | Low |
| TD-009 | MLX Llama-3.2-3B 4-bit | ✅ | 4 | High (~100 tok/s) | Low |
| TD-010 | Test Coverage 80% | ✅ | 4 | High (181 tests) | None |
| TD-011 | Config-Driven VLM Rules | ✅ | 4 | Medium (no-code config) | None |
| TD-012 | FastAPI + htmx Dashboard | ✅ | 4 | Medium (monitoring) | Low |
| TD-013 | SQLite Persistence | ✅ | 5 | Medium (restart survival) | None |
| TD-014 | mTLS gRPC Security | ✅ | 5 | High (production security) | Low |
| TD-015 | mlx-vlm Multimodal | ✅ | 5 | High (image understanding) | Low |
| TD-016 | Async VLM Queue | ✅ | 5 | Medium (non-blocking) | Low |
| TD-017 | Prometheus Metrics | ✅ | 6 | High (observability) | None |
| TD-018 | Circuit Breaker | ✅ | 6 | High (reliability) | Low |
| TD-019 | Multi-Camera Round-Robin | ✅ | 7 | Medium (parallel capture) | Low |
| TD-020 | Detection Dedup IoU+TTL | ✅ | 7 | Medium (reduce duplicates) | Low |
| TD-021 | VLM Batch Accumulator | ✅ | 7 | High (throughput) | Low |
| TD-022 | Cloud Storage Lazy-Load | ✅ | 7 | Medium (graceful degrade) | None |
| TD-023 | OTel No-Op Fallback | ✅ | 7 | Low (optional tracing) | None |
| TD-024 | Grafana Provisioning | ✅ | 7 | Medium (monitoring) | Low |
| TD-025 | Custom Exception Hierarchy | ✅ | 8 | Medium (error handling) | None |
| TD-026 | Config Validation | ✅ | 8 | Medium (safety) | None |
| TD-027 | Graceful Shutdown | ✅ | 8 | High (reliability) | Low |
| TD-028 | NPU 3-Core Scheduling | ✅ | 8 | Medium (throughput) | Low |
| TD-029 | RTSP Source HAL | ✅ | 8 | Medium (flexibility) | Low |
| TD-030 | Event-Triggered Recording | ✅ | 8 | Medium (forensics) | Low |
| TD-031 | Token Bucket Rate Limiting | ✅ | 9 | High (security) | Low |
| TD-032 | Protobuf Input Validation | ✅ | 9 | High (security) | None |
| TD-033 | Dashboard HTTP Basic Auth | ✅ | 9 | Medium (security) | None |
| TD-034 | Session Cleanup Scheduling | ✅ | 9 | Medium (reliability) | None |
| TD-035 | OTel Span Hot Path | ✅ | 9 | Low (observability) | None |

---

### TD-008: Bidirectional Streaming for Control Commands

**Date**: 2026-02-14 (Week 3.5)
**Status**: ✅ Implemented
**Context**: 中心侧需要向边缘侧下发控制指令（调整阈值、切换模型）

**Decision**: Option 1 — Bidirectional Streaming

**Rationale**:
- Protobuf 接口已预留 `BidirectionalEventStream`
- 实现成本低（修改 ~50 行代码）
- 延迟低（< 10ms）

**Result**: BidirectionalEventStream supports DETECTION_ALERT, HEALTH_UPDATE, COMMAND_ACK, CONTROL_COMMAND events

**Implementation**: `rk3588-edge/src/communication/grpc_client.cpp`, `mac-central/src/communication/grpc_server.py`

---

### TD-009: MLX Model Selection — Llama-3.2-3B-Instruct 4-bit

**Date**: 2026-02-14 (Week 4)
**Status**: ✅ Implemented
**Context**: 需要选择合适的 MLX 模型进行语义分析

**Decision**: Option 1 — Llama-3.2-3B-Instruct, converted to MLX native 4-bit quantized

**Rationale**: 6.4GB → 1.7GB, ~100 tok/s, load 755ms, gen 326-1872ms

**Implementation**: `tools/convert_mlx_model.sh`, `mac-central/models/Llama-3.2-3B-Instruct-4bit-mlx/`

---

### TD-010: Test Coverage — 35 Python + 146 C++ tests

**Date**: 2026-02-14 (Week 4)
**Status**: ✅ Implemented
**Context**: Week 3 代码无单元测试，需要定义测试策略

**Decision**: Option 2 — 80% target

**Result**: 35 Python tests (unit + integration + real MLX), 146 C++ tests, 24 gRPC-specific tests

---

### TD-011: Config-Driven VLM Trigger Rules

**Date**: 2026-02-14 (Week 4)
**Status**: ✅ Implemented
**Context**: VLMTriggerRule dataclass existed but defaults were hardcoded, not loaded from config

**Decision**: Wire vlm_rules section in config.yaml → AppConfig → CentralOrchestrator

**Rationale**: Users can add/modify/remove VLM trigger rules without code changes

**Implementation**: `config.yaml`, `mac-central/src/config.py`, `mac-central/src/main.py`

---

### TD-012: FastAPI + htmx Dashboard (Minimal Dependencies)

**Date**: 2026-02-14 (Week 4)
**Status**: ✅ Implemented
**Context**: Need simple monitoring dashboard, no heavy frontend framework

**Decision**: FastAPI backend + htmx for reactivity + WebSocket for live events

**Alternatives Considered**:
1. React/Vue SPA (overkill)
2. Grafana (external dependency)
3. Plain HTML polling (no real-time)

**Rationale**: ~80 lines Python + ~60 lines HTML, zero build step, minimal deps (fastapi, uvicorn, jinja2)

**Implementation**: `extensions/dashboard/`

---

### TD-013: SQLite for Detection Persistence

**Date**: 2026-02-14 (Week 5)
**Status**: ✅ Implemented
**Context**: Detection events stored only in memory deque(maxlen=100), lost on restart

**Decision**: SQLite with thread-safe wrapper (threading.Lock), timestamp-indexed

**Alternatives Considered**:
1. PostgreSQL (overkill for single-node)
2. Redis (volatile by default, adds dependency)
3. File-based JSON logs (no query capability)

**Rationale**: Zero external dependencies, ACID, built-in Python support, sufficient for single-server workload

**Implementation**: `mac-central/src/storage/detection_store.py`

---

### TD-014: mTLS for gRPC Security

**Date**: 2026-02-14 (Week 5)
**Status**: ✅ Implemented
**Context**: gRPC using insecure channel, no encryption or authentication

**Decision**: Optional mTLS via config toggle (`tls.enabled`), self-signed CA

**Alternatives Considered**:
1. Token-based auth (no encryption)
2. WireGuard VPN (network-level, more complex)
3. Always-on TLS (breaks local dev)

**Rationale**: Config-driven toggle preserves dev ergonomics while enabling production security

**Implementation**: `tools/certs/generate_certs.sh`, `grpc_server.py`, `grpc_client.cpp`

---

### TD-015: mlx-vlm for Multimodal VLM

**Date**: 2026-02-14 (Week 5)
**Status**: ✅ Implemented
**Context**: `analyze_image()` ignored image data, only did text inference

**Decision**: Dual-mode engine — `mode="llm"` (mlx_lm) or `mode="vlm"` (mlx_vlm)

**Alternatives Considered**:
1. OpenAI API (latency, cost, privacy)
2. llama.cpp multimodal (less Apple Silicon optimized)
3. Single VLM-only mode (breaks existing LLM workflow)

**Rationale**: mlx_vlm native Apple Silicon, graceful fallback to LLM, config-driven

**Implementation**: `mac-central/src/llm_vlm/mlx_llm_inference.py`

---

### TD-016: Async VLM Queue

**Date**: 2026-02-14 (Week 5)
**Status**: ✅ Implemented
**Context**: Synchronous VLM inference (326ms-1.9s) blocked gRPC stream processing

**Decision**: asyncio.Queue + background worker task for VLM inference

**Alternatives Considered**:
1. Thread pool (GIL contention with MLX)
2. Process pool (IPC overhead for large images)
3. Fire-and-forget tasks (no backpressure)

**Rationale**: Bounded queue (maxsize=32) provides backpressure, serial worker avoids MLX contention

**Implementation**: `mac-central/src/application_logic/central_orchestrator.py`

---

### TD-017: Prometheus Metrics Export

**Date**: 2026-02-14 (Week 6)
**Status**: ✅ Implemented
**Context**: No runtime observability — can't monitor inference latency, error rates, or resource usage in production

**Decision**: Prometheus-compatible /metrics endpoint with counters, histograms, and gauges

**Alternatives Considered**:
1. StatsD (push model, extra infra)
2. Custom JSON endpoint (no ecosystem)
3. OpenTelemetry (overkill for single-node)

**Rationale**: Pull-based, zero external deps, Grafana-compatible, Python prometheus_client library

**Implementation**: `mac-central/src/observability/metrics.py`

---

### TD-018: Circuit Breaker for VLM Inference

**Date**: 2026-02-14 (Week 6)
**Status**: ✅ Implemented
**Context**: VLM inference failures (OOM, timeout) could cascade and block all detection processing

**Decision**: 3-state circuit breaker (closed → open → half_open) wrapping VLM calls

**Alternatives Considered**:
1. Simple retry (no backoff, hammers failing service)
2. Bulkhead (process isolation, IPC overhead)
3. Rate limiter (doesn't handle failures)

**Rationale**: Prevents cascade failures, auto-recovers after cooldown (30s), minimal code (~60 lines)

**Implementation**: `mac-central/src/observability/circuit_breaker.py`

---

### TD-019: Multi-Camera Round-Robin Capture

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: Single-camera pipeline limits coverage, need multiple cameras per edge device

**Decision**: Vector of V4L2 cameras with round-robin capture scheduling

**Alternatives Considered**:
1. Parallel capture threads (high CPU, complex sync)
2. Single camera with external multiplexer (hardware dependency)
3. Round-robin in main loop ✅ (simple, low overhead)

**Rationale**: Sequential capture with shared NPU (mutex-protected) balances throughput and complexity

**Implementation**: `rk3588-edge/src/app/pipeline_coordinator.cpp`

---

### TD-020: Detection Deduplication via IoU + TTL

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: Multi-camera overlapping views cause duplicate detections

**Decision**: Cache-based deduplication with IoU spatial matching + TTL temporal coherence

**Alternatives Considered**:
1. No dedup (accept duplicates)
2. Spatial-only (misses temporal duplicates)
3. IoU + TTL ✅ (handles both spatial and temporal)

**Rationale**: IoU threshold 0.5-0.7 filters spatial duplicates, TTL 2-5s filters temporal duplicates

**Implementation**: `rk3588-edge/src/ai_inference/detection_dedup_cache.cpp`

---

### TD-021: VLM Batch Accumulator

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: Per-request VLM inference has high overhead (model load, tokenization)

**Decision**: Accumulator worker with configurable batch_size + timeout

**Alternatives Considered**:
1. No batching (high latency per request)
2. Fixed batch size (may wait too long)
3. Batch size + timeout ✅ (balances latency and throughput)

**Rationale**: Batch size 4-8 reduces per-request overhead, timeout 1-2s ensures responsiveness

**Implementation**: `mac-central/src/llm_vlm/vlm_batch_worker.py`

---

### TD-022: Cloud Storage Lazy-Load boto3

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: boto3 is large dependency (~50MB), not all deployments need cloud storage

**Decision**: Lazy import boto3 only when cloud_storage.enabled=true

**Alternatives Considered**:
1. Always import (bloats minimal installs)
2. Optional dependency (pip install complexity)
3. Lazy import ✅ (graceful degradation)

**Rationale**: System works without boto3, logs warning if storage unavailable

**Implementation**: `mac-central/src/storage/cloud_storage.py`

---

### TD-023: OpenTelemetry No-Op Fallback

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: OTel adds tracing overhead, not all deployments need distributed tracing

**Decision**: Lazy-load OTel with no-op tracer fallback if unavailable

**Alternatives Considered**:
1. Always require OTel (forces dependency)
2. Conditional imports with try/except ✅ (graceful)
3. Separate tracing service (adds complexity)

**Rationale**: Tracing is optional, system works without OTel

**Implementation**: `mac-central/src/observability/tracing.py`

---

### TD-024: Grafana Dashboard Provisioning

**Date**: 2026-02-16 (Week 7)
**Status**: ✅ Implemented
**Context**: Manual Grafana setup is error-prone and not reproducible

**Decision**: Auto-provision datasource + dashboard via docker-compose volumes

**Alternatives Considered**:
1. Manual setup (not reproducible)
2. Grafana API scripts (complex)
3. Provisioning YAML ✅ (declarative, version-controlled)

**Rationale**: Dashboard JSON + datasource YAML in git, auto-loaded on startup

**Implementation**: `extensions/monitoring/grafana/provisioning/`

---

### TD-025: Custom Exception Hierarchy

**Date**: 2026-02-16 (Week 8)
**Status**: ✅ Implemented
**Context**: Broad `except Exception` blocks masked real errors

**Decision**: NeuroPipelineError base class + 5 typed subtypes (Config, Inference, Communication, Storage, Security)

**Rationale**: Specific exception types enable targeted error handling and better diagnostics

**Implementation**: `mac-central/src/exceptions.py`

---

### TD-031: Token Bucket Rate Limiting

**Date**: 2026-02-16 (Week 9 / v1.3.0)
**Status**: ✅ Implemented
**Context**: No protection against edge device flooding central server

**Decision**: Per-device token bucket rate limiter with configurable max_rps and burst

**Alternatives Considered**:
1. Fixed window counter (bursty, unfair)
2. Sliding window (complex, memory-heavy)
3. Token bucket ✅ (smooth, per-device isolation)

**Rationale**: Smooth rate limiting with burst tolerance, O(1) per request, per-device isolation

**Implementation**: `mac-central/src/communication/rate_limiter.py`

---

### TD-032: Protobuf Input Validation

**Date**: 2026-02-16 (Week 9 / v1.3.0)
**Status**: ✅ Implemented
**Context**: No server-side validation of incoming DetectionResult messages

**Decision**: Validate device_id, confidence [0,1], coordinates [0,1] before processing

**Rationale**: Defense in depth — reject malformed data at the boundary

**Implementation**: `mac-central/src/communication/grpc_server.py:_validate_detection()`

---

### TD-033: Dashboard HTTP Basic Auth

**Date**: 2026-02-16 (Week 9 / v1.3.0)
**Status**: ✅ Implemented
**Context**: Dashboard exposed without authentication

**Decision**: HTTP Basic Auth via environment variables, /healthz exempt

**Rationale**: Simple, no external auth service needed, credentials not in config files

**Implementation**: `extensions/dashboard/app.py`

---

## References

- Architecture Design: `docs/ARCHITECTURE.md`
- Week 1 Retro: `docs/devlog/week1-retro.md`
- Week 2 Retro: `docs/devlog/week2-retro.md`
- Week 3 Completion: `docs/devlog/WEEK3_COMPLETION_SUMMARY.md`
- Performance Benchmark: `docs/performance/week3-benchmark.md`
- KPI Report: `docs/performance/kpi-report.md`
- Week 8 Production Hardening: v1.2.0
- Week 9 Security + Activation: v1.3.0
