# Neuro-Pipeline Architecture Design

**Version**: 1.0.0
**Date**: 2026-02-11
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
│      central_orchestrator.py / event_processor.py     │
├─────────────────────────────────────────────────────┤
│              Layer 4: Communication                  │
│         grpc_server.py / stream_handler.py            │
├─────────────────────────────────────────────────────┤
│              Layer 3: AI Inference                    │
│   mlx_llm_inference.py / prompt_generator.py          │
├─────────────────────────────────────────────────────┤
│              Layer 2: Data Processing                │
│            data_converter.py                          │
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
| **Model Format** | .rknn (INT8 quantized) | MLX quantized (4-bit) |
| **Communication** | gRPC C++ | gRPC Python (asyncio) |
| **Serialization** | Protobuf 3 | Protobuf 3 |
| **Testing** | GoogleTest | pytest |
| **Logging** | spdlog (planned) | Python logging / structlog |

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
| Central VLM Inference | < 2s | MLX profiler |
| Edge Memory Footprint | < 512MB | /proc/meminfo |
| NPU Utilization | > 70% | /sys/kernel/debug/rknpu/load |

---

## 8. Security Considerations

- **mTLS**: gRPC 通道使用双向 TLS 认证
- **Input Validation**: 所有 Protobuf 消息校验
- **Resource Limits**: 有界缓冲池防止 DoS
- **Least Privilege**: 边缘进程以非 root 用户运行
- **Buffer Overflow Prevention**: RAII + bounds checking

---

## 9. Future Extensions

- 多摄像头支持
- 模型热替换（无需重启更新 YOLO）
- 云存储集成（S3 / GCS）
- Web Dashboard 实时监控
- 多边缘节点聚合到单中心服务器
- Kubernetes 边缘部署 (KubeEdge)

---

## 10. Reference Projects

| Project | Relevance |
|---|---|
| [airockchip/rknpu2](https://github.com/airockchip/rknpu2) | 零拷贝 API 基础 |
| [nyanmisaka/ffmpeg-rockchip](https://github.com/nyanmisaka/ffmpeg-rockchip) | MPP+RGA 零拷贝管线参考 |
| [kaylorchen/rk3588-yolo-demo](https://github.com/kaylorchen/rk3588-yolo-demo) | 多线程 YOLO 100FPS |
| [ml-explore/mlx](https://github.com/ml-explore/mlx) | Apple Silicon ML 框架 |
| [ScorcaF/Edge-Cloud-Collaborative-Inference](https://github.com/ScorcaF/Edge-Cloud-Collaborative-Inference) | 边缘-云协同推理 |
