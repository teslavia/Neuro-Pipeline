# Neuro-Pipeline Architecture Design

**Version**: 1.3.0
**Date**: 2026-02-16
**Author**: Teslavia

---

## 1. Design Principles

| Principle | Description |
|---|---|
| **High Cohesion, Low Coupling** | 各模块职责单一，对外接口清晰 |
| **Layered Architecture** | HAL → Data Processing → AI Inference → Communication → Application |
| **Heterogeneous Collaboration** | RK3588 边缘计算 + Apple Silicon 云端推理 |
| **Zero-Copy Data Flow** | DMA-BUF 机制最小化内存拷贝，降低延迟 |
| **Event-Driven** | 边缘侧仅在关键事件触发时上报，节省带宽 |
| **Extensibility** | 模块化设计支持新传感器、模型、云服务扩展 |
| **Observability** | 全链路日志、指标、调试钩子 |

---

## 2. System Layers

### 2.1 RK3588 Edge Device (5 Layers)

```
┌─────────────────────────────────────────────────────┐
│              Layer 5: Application Logic              │
│         edge_main.cpp / pipeline_coordinator.cpp     │
├─────────────────────────────────────────────────────┤
│              Layer 4: Communication                  │
│         grpc_client.cpp / event_publisher.cpp         │
├─────────────────────────────────────────────────────┤
│              Layer 3: AI Inference                    │
│      rknn_engine.cpp / yolo_postprocess.cpp           │
├─────────────────────────────────────────────────────┤
│              Layer 2: Data Processing                │
│    zero_copy_buffer.cpp / memory_pool.cpp             │
├─────────────────────────────────────────────────────┤
│        Layer 1: Hardware Abstraction (HAL)            │
│    v4l2_camera.cpp / mpp_decoder.cpp / rga_processor  │
└─────────────────────────────────────────────────────┘
```

#### Layer 1: Hardware Abstraction (HAL)
- **Location**: `rk3588-edge/src/hal/`, `include/rk_hal/`
- **Components**:
  - `v4l2_camera.cpp` — V4L2 视频捕获，MMAP/DMABUF 模式
  - `mpp_decoder.cpp` — Rockchip MPP 硬件视频解码
  - `rga_processor.cpp` — RGA 2D 图像处理（缩放、裁剪、格式转换）
  - `drm_allocator.cpp` — DRM/DMA-BUF 内存分配管理
- **Key Technologies**: V4L2, MPP, RGA, DRM, CMA, DMA-BUF

#### Layer 2: Data Processing
- **Location**: `rk3588-edge/src/data_processing/`
- **Components**:
  - `zero_copy_buffer.cpp` — 统一缓冲池，DMA-BUF fd 共享
  - `memory_pool.cpp` — 固定大小内存池，可预测分配
  - `thread_pool.cpp` — 工作线程池，并行处理
- **Key Technologies**: DMA-BUF, mmap, RAII, std::shared_ptr

#### Layer 3: AI Inference
- **Location**: `rk3588-edge/src/ai_inference/`
- **Components**:
  - `rknn_engine.cpp` — RKNN 模型加载、NPU 核心管理
  - `yolo_postprocess.cpp` — YOLO 输出解析、NMS、边界框解码
  - `npu_scheduler.cpp` — 多核 NPU 任务调度
- **Key Technologies**: RKNN API 2.0, INT8 量化, NMS 算法

#### Layer 4: Communication
- **Location**: `rk3588-edge/src/communication/`
- **Components**:
  - `grpc_client.cpp` — gRPC 客户端，含重连逻辑
  - `video_streamer.cpp` — 视频帧流式传输，含流控
  - `event_publisher.cpp` — 事件驱动通知系统
- **Key Technologies**: gRPC, Protobuf, HTTP/2, Keepalive

#### Layer 5: Application Logic
- **Location**: `rk3588-edge/src/app/`
- **Components**:
  - `edge_main.cpp` — 主入口
  - `pipeline_coordinator.cpp` — 编排数据流穿越各层
  - `config_manager.cpp` — 配置文件解析

### 2.2 Mac Mini Central Server (5 Layers)

```
┌─────────────────────────────────────────────────────┐
│              Layer 5: Application Logic              │
│  central_orchestrator.py / dashboard (FastAPI+htmx)  │
├─────────────────────────────────────────────────────┤
│              Layer 4: Communication                  │
│         grpc_server.py / stream_handler.py            │
├─────────────────────────────────────────────────────┤
│              Layer 3: AI Inference                    │
│   mlx_llm_inference.py / prompt_generator.py          │
├─────────────────────────────────────────────────────┤
│              Layer 2: Data Processing                │
│         data_converter.py / SQLite + Metrics         │
├─────────────────────────────────────────────────────┤
│       Layer 1: OS / Hardware (Apple Silicon)          │
│          UMA / Neural Engine / GPU                    │
└─────────────────────────────────────────────────────┘
```

---

## 3. Zero-Copy Pipeline (RK3588)

```
V4L2 Camera          MPP Decoder           RGA Processor         RKNN NPU
┌───────────┐       ┌────────────┐       ┌──────────────┐      ┌──────────┐
│ /dev/videoX│──────►│ DMA Buffer │──────►│  DMA Buffer  │─────►│DMA Buffer│
│  (MMAP)   │       │  (NV12)    │       │   (RGB888)   │      │ (Tensor) │
└───────────┘       └────────────┘       └──────────────┘      └──────────┘
     │                    │                      │                   │
     └────────────────────┴──────────────────────┴───────────────────┘
                       DMA-BUF File Descriptor Passing
                       (Zero Memory Copy Between Components)
```

**关键设计**:
- 所有硬件加速器通过 DMA-BUF fd 共享同一块物理内存
- CPU 仅参与控制面（ioctl），不参与数据面拷贝
- 缓存一致性通过显式 `SyncForDevice()` / `SyncForCPU()` 管理

---

## 4. Edge-Cloud Communication Flow

```
RK3588 Edge                                    Mac Mini Central
┌─────────────────┐                           ┌──────────────────┐
│ Video Capture   │                           │                  │
└────────┬────────┘                           │                  │
         │                                    │                  │
         ▼                                    │                  │
┌─────────────────┐                           │                  │
│ YOLO Detection  │                           │                  │
└────────┬────────┘                           │                  │
         │                                    │                  │
         ▼                                    │                  │
┌─────────────────┐                           │                  │
│ Event Filter    │───► Critical Event? ────► │ gRPC Server      │
│ (Confidence &   │        YES (frame+meta)   │                  │
│  Rule Engine)   │                           └────────┬─────────┘
└─────────────────┘                                    │
                          ┌────────────────────────────┘
                          ▼
                 ┌─────────────────┐
                 │ MLX VLM Inference│
                 │ (Semantic Analyze)│
                 └────────┬─────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Action Decision  │──► Alert / Log / Command
                 └─────────────────┘
```

---

## 5. Technology Stack

| Component | RK3588 Edge | Mac Mini Central |
|---|---|---|
| **Language** | C++17 | Python 3.10+ |
| **Build System** | CMake 3.20+ | setuptools / pip |
| **Video Capture** | V4L2 | — |
| **Video Decode** | MPP (Hardware) | — |
| **Image Processing** | RGA (Hardware) | OpenCV / Pillow |
| **AI Framework** | RKNN NPU (6 TOPS) | MLX (Apple Silicon) |
| **Model Format** | .rknn (INT8 quantized) | MLX native (4-bit quantized) |
| **Communication** | gRPC C++ | gRPC Python (asyncio) |
| **Serialization** | Protobuf 3 | Protobuf 3 |
| **Testing** | GoogleTest | pytest |
| **Logging** | spdlog (planned) | Python logging / structlog |
| **Dashboard** | — | FastAPI + htmx + WebSocket |

---

## 6. Key Design Decisions

### Decision 1: Zero-Copy Architecture
- **Choice**: DMA-BUF for zero-copy data sharing
- **Rationale**: 最小化嵌入式设备上的 CPU 负载和内存带宽占用
- **Trade-off**: 缓冲区生命周期管理复杂度增加

### Decision 2: Event-Driven Communication
- **Choice**: 边缘侧仅在显著事件触发时发送数据
- **Rationale**: 减少 90%+ 的网络带宽消耗
- **Trade-off**: 需要边缘侧智能过滤逻辑

### Decision 3: Heterogeneous Deployment
- **Choice**: 轻量模型部署在边缘，重型模型部署在中心
- **Rationale**: YOLO 适配 NPU 内存，VLM 需要 16GB+ 统一内存
- **Trade-off**: 中心推理结果存在网络延迟

### Decision 4: gRPC over Custom Protocol
- **Choice**: 所有通信使用 gRPC
- **Rationale**: HTTP/2 多路复用、内置流控、跨语言绑定
- **Trade-off**: 相比原始 TCP 有少量开销（本场景可接受）

### Decision 5: C++17 for Edge
- **Choice**: C++17 标准
- **Rationale**: std::optional, std::variant, 结构化绑定等现代特性，同时确保 RK3588 工具链兼容
- **Trade-off**: 不使用 C++20 (部分交叉编译器支持不完善)

---

## 7. Performance Targets

| Metric | Target | Measurement Method |
|---|---|---|
| Edge Inference Latency | < 20ms | RKNN profiler |
| Video Frame Rate | 30 FPS (1080p) | Frame counter |
| Network Round-Trip | < 100ms | gRPC timestamps |
| Central VLM Inference | < 2s (achieved: 326ms-1.9s) | MLX profiler |
| Edge Memory Footprint | < 512MB | /proc/meminfo |
| NPU Utilization | > 70% | /sys/kernel/debug/rknpu/load |
| MLX Model Load | < 3s | mlx_lm.load() timer |

---

## 8. Security Considerations

- **mTLS**: gRPC 通道使用双向 TLS 认证
- **Input Validation**: 所有 Protobuf 消息校验
- **Resource Limits**: 有界缓冲池防止 DoS
- **Least Privilege**: 边缘进程以非 root 用户运行
- **Buffer Overflow Prevention**: RAII + bounds checking
- **Rate Limiting**: gRPC token bucket per-device rate limiting
- **Input Validation**: Protobuf field validation (device_id, coordinates, confidence)
- **Dashboard Auth**: HTTP Basic Auth for web dashboard
- **Audit Logging**: Structured audit trail for control commands

---

## 9. Future Extensions

- Kubernetes 边缘部署 (KubeEdge)
- 边缘侧模型自动更新

---

## 10. Reference Projects

| Project | Relevance |
|---|---|
| [airockchip/rknpu2](https://github.com/airockchip/rknpu2) | 零拷贝 API 基础 |
| [nyanmisaka/ffmpeg-rockchip](https://github.com/nyanmisaka/ffmpeg-rockchip) | MPP+RGA 零拷贝管线参考 |
| [kaylorchen/rk3588-yolo-demo](https://github.com/kaylorchen/rk3588-yolo-demo) | 多线程 YOLO 100FPS |
| [ml-explore/mlx](https://github.com/ml-explore/mlx) | Apple Silicon ML 框架 |
| [ScorcaF/Edge-Cloud-Collaborative-Inference](https://github.com/ScorcaF/Edge-Cloud-Collaborative-Inference) | 边缘-云协同推理 |

---

## 11. Observability (v1.0.0)

### Prometheus Metrics
- **Counters**:
  - `detections_total` — 累计检测次数
  - `grpc_calls_total` — gRPC 调用次数（按方法和状态分类）
  - `vlm_inferences_total` — VLM 推理次数
- **Histograms**:
  - `inference_latency_seconds` — 推理延迟分布（YOLO/VLM）
  - `grpc_request_duration_seconds` — gRPC 请求耗时
- **Gauges**:
  - `npu_utilization_percent` — NPU 利用率（边缘侧）
  - `vlm_queue_depth` — VLM 队列深度（中心侧）
  - `active_connections` — 活跃 gRPC 连接数
- **Endpoint**: `/metrics` (Prometheus 文本格式)

### Health Probes
- **Liveness Probe** (`/healthz`): 进程存活检查，返回 200 OK
- **Readiness Probe** (`/readyz`): 服务就绪检查（模型加载、gRPC 监听、数据库连接）

### Circuit Breaker
- **States**: Closed (正常) → Open (熔断) → Half-Open (试探)
- **Trigger**: VLM 推理连续失败 N 次后进入 Open 状态
- **Recovery**: Half-Open 状态下成功 M 次后恢复 Closed
- **Fallback**: Open 状态下直接返回降级响应，避免级联故障

### Retry Patterns
- **Async Retry**: VLM 推理失败时指数退避重试（最多 3 次）
- **Sync Retry**: SQLite 锁冲突时短延迟重试（最多 5 次）
- **Backoff**: 初始 100ms，每次翻倍，最大 3.2s

### Alerting
- **CRITICAL Log**: 关键错误自动记录到日志（VLM 熔断、数据库故障）
- **Webhook POST**: 可选 HTTP POST 通知外部系统（配置 `alerting.webhook_url`）
- **Cooldown**: 同类告警 5 分钟内最多发送 1 次，防止告警风暴

---

## v1.1.0 Additions (Week 7)

### Multi-Camera Support (Edge)
- Vector of V4L2 cameras, round-robin capture
- Per-camera RGA processor, shared NPU with mutex
- Detection deduplication cache (IoU + TTL temporal coherence)

### Multi-Edge Device Sessions (Central)
- DeviceSessionManager: register/heartbeat/expiry
- Per-device conversation context for VLM
- Max devices limit with graceful rejection

### Model Hot-Swap (Edge)
- RELOAD_MODEL gRPC command
- Mutex-protected engine swap, zero downtime
- Config reload without restart

### VLM Batch Inference (Central)
- Accumulator worker: configurable batch_size + timeout
- Multi-turn conversation context per device
- Batch processing reduces per-request overhead

### Cloud Storage Integration (Central)
- S3/MinIO async upload (lazy boto3 import)
- Graceful degradation if storage unavailable
- Configurable bucket + credentials

### Distributed Tracing (Central)
- OpenTelemetry init + span instrumentation
- Lazy-load with no-op fallback if unavailable
- Trace ID propagation via gRPC metadata

### Structured Logging (Edge)
- C++ logger.hpp JSON output mode
- Configurable via `logging.format` in config

### Grafana Monitoring Stack
- 8-panel dashboard (detections, latency, NPU, VLM queue, etc.)
- Prometheus + docker-compose deployment
- Auto-provisioned datasource + dashboard

### Dashboard Multi-Device (Central)
- `/api/devices` endpoint lists all registered devices
- `device_id` filter for events/history
- Multi-device grid view

### Chaos + E2E Tests
- Disconnect recovery, circuit breaker, SQLite retry
- Session expiry, VLM queue overflow
- Synthetic pipeline validation (250 Python tests total)

### Load Testing
- Locust gRPC load test (N edge devices simulation)
- GitHub Actions workflow_dispatch trigger
- Configurable users/spawn-rate/duration

---

## v1.3.0 Additions

### Session Cleanup Scheduling
- Periodic cleanup of expired device sessions in main.py
- Prometheus gauge update for expired devices

### Edge Event Dispatch
- handle_edge_event() routes HEALTH_UPDATE → metrics, SYSTEM_ERROR → alerts
- Previously empty stub now fully functional

### gRPC Token Bucket Rate Limiting
- Per-device rate limiting with burst capacity
- Returns RESOURCE_EXHAUSTED on exceed

### Protobuf Input Validation
- device_id non-empty, coordinates [0,1], confidence [0,1]
- Validation errors tracked via Prometheus counter

### Dashboard HTTP Basic Auth
- Environment variable credentials (DASHBOARD_USER/DASHBOARD_PASS)
- /healthz exempt from authentication

### Control Command Audit Logging
- Structured JSON audit entries for all control commands
- Prometheus counter for command types

### Dead Code Activation (Edge C++)
- RTSP source wired into pipeline coordinator
- Video recorder triggered on novel detections
- Memory pool PoolGuard RAII pattern
- NPU scheduler replaces manual bitmask

### Database Optimization
- Composite index on (device_id, timestamp)
- Created after migration for legacy DB compatibility

### OTel Span Instrumentation
- process_detection() and vlm_inference() wrapped with spans
- No-op fallback when OTel unavailable

### CI C++ Tests
- Native x86_64 + mock HAL + GoogleTest job in CI
- ctest --output-on-failure

---

## v1.2.0 Additions (Week 8)

### Custom Exception Hierarchy
- NeuroPipelineError base + 5 subtypes (ConfigError, InferenceError, CommunicationError, StorageError, SecurityError)
- Replaced 8 broad `except Exception` with specific types

### Config Validation
- Port range, confidence bounds, timeout positivity, TLS file existence
- inference_mode enum, cloud storage provider validation

### Graceful Shutdown
- VLM queue drain with configurable timeout
- Global 60-second shutdown limit

### Edge Prometheus Metrics (C++)
- Atomic counters, histograms, gauges in C++ pipeline
- Frame count, inference latency, NPU utilization

### NPU 3-Core Scheduling
- Round-robin core assignment per camera index
- Replaces manual `1 << (cam_idx % 3)` bitmask

### RTSP Source HAL Module
- FFmpeg-based RTSP input (placeholder + mock)
- Auto-detected via `rtsp://` prefix in video_source config

### Event-Triggered Video Recorder
- Ring buffer (pre_seconds) + post-trigger recording (post_seconds)
- Configurable output directory

### SQLite Atomic Backup
- sqlite3.backup() API for consistent snapshots
- Scheduled periodic backup via async task

### Alert Severity Routing
- INFO/WARNING/CRITICAL severity levels
- Per-severity webhook URL routing

---

## v0.5.0–v1.0.0 Additions

### Week 5 (v0.5.0)

#### Storage Layer
- SQLite-based DetectionStore (`mac-central/src/storage/detection_store.py`)
- Thread-safe with threading.Lock, WAL mode
- Schema: detections table with timestamp index
- Injected into CentralOrchestrator via constructor

### Dual-Mode Inference Engine
- `mode="llm"`: text-only via mlx_lm (existing)
- `mode="vlm"`: vision-language via mlx_vlm (Qwen2-VL)
- `analyze_image()` uses real VLM when available, falls back to LLM
- Configured via `central.inference_mode` and `central.vlm_model_path`

### Async VLM Queue
- `process_detection()` enqueues VLM work to `_vlm_queue` (non-blocking)
- `_vlm_worker()` background task consumes queue serially
- Prevents VLM latency (326ms-1.9s) from blocking gRPC stream processing

### mTLS Security
- Optional mTLS for gRPC (config-driven `tls.enabled`)
- Certificate generation: `tools/certs/generate_certs.sh`
- Server: `grpc.ssl_server_credentials` with client auth
- Client: `grpc::SslCredentials` with mutual authentication

### Edge Frame Skip
- `edge.frame_skip_interval` config: send every Nth frame to central
- Reduces central server load for high-FPS edge streams

### Week 6 (v1.0.0)

#### Prometheus Metrics Export
- Counters: `detections_total`, `grpc_calls_total`, `vlm_inferences_total`
- Histograms: `inference_latency_seconds`, `grpc_request_duration_seconds`
- Gauges: `npu_utilization_percent`, `vlm_queue_depth`, `active_connections`
- `/metrics` endpoint for Prometheus scraping

#### Health Probes
- `/healthz`: Liveness probe (进程存活)
- `/readyz`: Readiness probe (服务就绪，含模型加载、gRPC、数据库检查)

#### Circuit Breaker
- 3-state (Closed/Open/Half-Open) for VLM inference
- Prevents cascade failures when VLM service degrades
- Configurable failure threshold and recovery attempts

#### Retry Patterns
- Async retry with exponential backoff for VLM inference (max 3 attempts)
- Sync retry for SQLite lock conflicts (max 5 attempts)
- Backoff: 100ms → 200ms → 400ms → ... (max 3.2s)

#### Alerting
- CRITICAL log for key failures (VLM circuit open, DB errors)
- Optional webhook POST to external systems (configurable URL)
- Cooldown mechanism: max 1 alert per type per 5 minutes
