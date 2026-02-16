<h1 align="center">Neuro-Pipeline</h1>

<p align="center">
  <b>异构 AI 推理系统 — RK3588 NPU 边缘 + Apple Silicon 中心</b>
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
  <b>中文</b> | <a href="README_EN.md">English</a>
</p>

---

```
Camera --> V4L2 --> MPP --> RGA --> RKNN NPU --> gRPC --> MLX VLM --> Alert
           capture  decode  resize  YOLO detect  stream   analyze    action
           |<--- zero-copy DMA-BUF --->|         |<- mTLS ->|
```

## 亮点

| | 边缘端 (RK3588) | 中心端 (Mac Mini) |
|---|---|---|
| **硬件** | 6 TOPS NPU, 8 核 ARM | Apple Silicon 统一内存 |
| **AI 模型** | YOLOv5 INT8 (8.5 MB) | Llama-3.2-3B 4-bit (1.7 GB) |
| **框架** | RKNN SDK 2.0 | MLX + mlx-vlm |
| **语言** | C++17 / CMake | Python 3.10+ / asyncio |
| **延迟** | 20.3 ms 推理 | 326 ms – 1.9 s VLM |
| **吞吐** | 28.5 FPS @ 1080p | ~100 tok/s |

**核心能力：**
- **零拷贝 DMA-BUF 管线** — V4L2 → MPP → RGA → RKNN，全程无 CPU 内存拷贝
- **事件驱动上报** — 节省 96% 带宽，仅上传关键检测结果
- **双模态 VLM** — 纯文本 LLM 或视觉语言多模态推理 (Qwen2-VL)
- **mTLS gRPC** — 双向流式通信 + 双向 TLS 认证
- **可观测性** — Prometheus 指标、健康探针、熔断器、告警路由
- **SQLite 持久化** — 检测历史重启不丢失，原子备份，7 天自动清理
- **Web 仪表盘** — FastAPI + htmx + WebSocket 实时监控，HTTP Basic Auth 认证
- **多摄像头 + 多边缘** — 单中心管理多设备，多摄像头并行推理
- **VLM 批量推理** — 累积批处理 + 多轮对话上下文
- **云存储集成** — S3/MinIO 异步上传，分布式追踪 (OTel)
- **安全加固** — gRPC 令牌桶限流、Protobuf 输入校验、审计日志
- **RTSP 输入** — 支持网络摄像头 RTSP URL 接入
- **视频录制** — 事件触发录制 + 环形缓冲区
- **NPU 三核调度** — 按摄像头轮询分配 NPU 核心
- **优雅关闭** — VLM 队列排空 + 可配置超时

## 架构

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

**零拷贝数据流 (RK3588)：**

```
V4L2 Camera --> MPP Decoder --> RGA Processor --> RKNN NPU
     |               |               |               |
     +---------------+---------------+---------------+
              DMA-BUF fd passing (zero memory copy)
```

## 性能

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

| 指标 | 目标 | 实测 | 状态 |
|------|------|------|------|
| 边缘推理延迟 | < 30 ms | 20.3 ms | ✅ |
| 视频帧率 | ≥ 25 FPS | 28.5 FPS | ✅ |
| NPU 利用率 | > 60% | 72% | ✅ |
| 边缘内存 (RSS) | < 512 MB | ~280 MB | ✅ |
| 中心 VLM 吞吐 | — | ~100 tok/s | ✅ |
| MLX 模型加载 | < 3 s | 755 ms | ✅ |

## 快速开始

### 边缘端 — RK3588 交叉编译

```bash
# 组装 sysroot（从 RKSDK 提取头文件和库）
bash tools/cross_compile_env/prepare_sysroot.sh

# Docker 交叉编译（推荐）
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh

# 部署并运行
bash tools/deploy_and_run.sh
```

### 中心端 — Mac Mini 配置

```bash
cd mac-central
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 生成 Protobuf 绑定
python3 tools/generate_proto.py

# 启动服务
python -m src.main --config ../config.yaml
```

### 仪表盘

```bash
cd extensions/dashboard
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
# -> http://localhost:8080
```

## 项目结构

```
neuro-pipeline/
├── rk3588-edge/                   # 边缘端 (C++17)
│   ├── src/
│   │   ├── hal/                   #   V4L2, MPP, RGA, DRM, RTSP
│   │   ├── ai_inference/          #   RKNN, YOLO, NPU 调度器
│   │   ├── data_processing/       #   zero-copy buffer, pool
│   │   ├── communication/         #   gRPC client
│   │   └── app/                   #   pipeline coordinator, 录制器
│   ├── tests/                     #   GoogleTest (146 tests)
│   └── cmake/                     #   aarch64 toolchain
├── mac-central/                   # 中心端 (Python)
│   ├── src/
│   │   ├── communication/         #   gRPC async server, 限流器
│   │   ├── llm_vlm/               #   MLX LLM/VLM engine
│   │   ├── application_logic/     #   orchestrator, breaker
│   │   ├── storage/               #   SQLite, cloud storage
│   │   └── observability/         #   metrics, tracing, alerting
│   └── tests/                     #   pytest (247 tests: 209 unit + 38 e2e/chaos)
├── proto/                         # Protobuf definitions
├── extensions/
│   ├── dashboard/                 # FastAPI + htmx UI
│   └── monitoring/                # Grafana + Prometheus stack
├── tools/
│   ├── cross_compile_env/         #   Docker + sysroot
│   ├── certs/                     #   mTLS cert gen
│   └── services/                  #   systemd + launchd
├── config.yaml                    # unified config
└── VERSION.json                   # v1.3.0
```

## 测试覆盖

| 组件 | 框架 | 测试数 | 说明 |
|------|------|--------|------|
| C++ 边缘端 (Mock HAL) | GoogleTest | 146 | buffer, pool, thread, HAL, YOLO, gRPC |
| Python 中心端 | pytest | 250 | 212 unit + 38 e2e/chaos (8 skipped) |
| 合计 | — | 396+ | 跨编译 mock ON/OFF 均通过 |

## 技术栈

| | RK3588 边缘端 | Mac Mini 中心端 |
|---|---|---|
| 语言 | C++17 | Python 3.10+ |
| 构建 | CMake 3.20+ | pip / setuptools |
| 视频 | V4L2 + MPP (硬件解码) | — |
| 图像 | RGA (硬件缩放/转换) | Pillow |
| AI | RKNN NPU (6 TOPS) | MLX (Apple Silicon) |
| 模型 | .rknn INT8 量化 | MLX 4-bit 量化 |
| 通信 | gRPC C++ | gRPC Python (asyncio) |
| 指标 | — | Prometheus + /metrics |
| 存储 | — | SQLite (WAL mode) |
| 测试 | GoogleTest | pytest |

## 文档

| 文档 | 说明 |
|------|------|
| [架构设计](docs/ARCHITECTURE.md) | 5 层架构、零拷贝管线、数据流 |
| [API 参考](docs/API_REFERENCE.md) | gRPC 服务、REST 端点、HAL API |
| [部署指南](docs/DEPLOYMENT_GUIDE.md) | 交叉编译、设备部署、mTLS、系统服务 |
| [故障排查](docs/TROUBLESHOOTING.md) | 常见问题与解决方案 |
| [技术决策](docs/TECHNICAL_DECISIONS.md) | 24 条架构决策记录 (TD-001 ~ TD-024) |
| [KPI 报告](docs/performance/kpi-report.md) | 性能基准与管线分解 |

## 里程碑

| 版本 | 里程碑 | 核心交付 |
|------|--------|----------|
| v0.1.0 | 基础设施 | CMake, Docker toolchain, 8 modules, 101 tests |
| v0.2.0 | HAL + AI | V4L2/MPP/RGA/RKNN, 28.5 FPS, zero-copy |
| v0.3.0 | gRPC + MLX | bidirectional streaming, MLX engine |
| v0.4.0 | 生产加固 | 4-bit quantization, dashboard, config VLM |
| v0.5.0 | 生产部署 | mTLS, SQLite, VLM multimodal, async queue |
| v1.0.0 | 可观测性 | Prometheus, health probes, circuit breaker, alerting |
| v1.1.0 | 规模化 + 多边缘 | Multi-camera, multi-device, VLM batch, Grafana, chaos tests |
| v1.2.0 | 生产加固 | 异常体系、配置校验、优雅关闭、RTSP、视频录制 |
| v1.3.0 | 安全 + 激活 | 限流、输入校验、Dashboard 认证、审计日志、死代码激活 |

## 许可证

[MIT License](LICENSE) — Copyright (c) 2026 Teslavia
