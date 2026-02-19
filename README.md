<h1 align="center">Neuro-Pipeline</h1>

<p align="center">
  <b>异构 AI 推理系统 — RK3588 NPU 边缘 + Apple Silicon 中心</b>
</p>

<p align="center">
  <a href="https://github.com/teslavia/Neuro-Pipeline/actions"><img src="https://github.com/teslavia/Neuro-Pipeline/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-2.4.0-green.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-435+-brightgreen.svg" alt="Tests">
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
| **AI 模型** | YOLOv5/v8 INT8 (8–21 MB) | Llama-3.2-3B 4-bit (1.7 GB) |
| **框架** | RKNN SDK 2.0 | MLX + mlx-vlm |
| **语言** | C++17 / CMake | Python 3.10+ / asyncio |
| **延迟** | 20.3 ms 推理 | 326 ms – 1.9 s VLM |
| **吞吐** | 28.5 FPS @ 1080p | ~100 tok/s |

**核心能力：**
- **零拷贝 DMA-BUF 管线** — V4L2 → MPP → RGA → RKNN，全程无 CPU 内存拷贝
- **多模型热切换** — YOLOv5s/v5m/v8s 动态切换，NPU 三核独立加载，gRPC 远程触发
- **时序跟踪 + 行为分析** — IoU 匹配跨帧追踪，自动检测徘徊/奔跑/逗留行为
- **自适应帧率** — 根据检测密度动态调节 5–30 FPS，空闲时降频省电
- **事件驱动上报** — 节省 96% 带宽，仅上传关键检测结果
- **双模态 VLM** — 纯文本 LLM 或视觉语言多模态推理 (Qwen2-VL)
- **推理链 + RAG** — 三步推理（观察→推理→验证）+ 历史上下文检索增强
- **模型生命周期管理** — 部署/卸载/回滚/A-B 测试，gRPC ManageModel RPC
- **时序分析引擎** — 指标写入/查询/聚合，支持 FPS/延迟/检测数等维度
- **异常基线检测** — Z-score 异常检测，自动学习历史基线
- **mTLS gRPC** — 双向流式通信 + 双向 TLS 认证
- **RTSP 视频源** — 支持网络摄像机输入 (RTSP over TCP/UDP)
- **视频录制** — 关键事件触发录制，支持环形缓冲区预录
- **可观测性** — Prometheus 指标、健康探针、熔断器、告警路由、OTel 追踪
- **SQLite 持久化** — 检测历史重启不丢失，原子备份，7 天自动清理
- **Web 仪表盘** — FastAPI + htmx + WebSocket 实时监控，HTTP Basic Auth 认证
- **安全加固** — gRPC 令牌桶限流、Protobuf 输入校验、审计日志

## 架构

```
+------------------------------+                         +------------------------------+
|      RK3588 Edge Device      |    gRPC / mTLS / PB     |      Mac Mini Central        |
|      Embedded Linux / C++    | <=====================> |    macOS / Python / MLX       |
|                              |  detections, frames,    |                              |
|  +------------------------+  |  commands, VLM results  |  +------------------------+  |
|  | L5  Pipeline Coord     |  |                         |  | L5  Orchestrator       |  |
|  | L4  gRPC Client        |  |                         |  | L4  gRPC Server        |  |
|  | L3  Multi-Model NPU    |  |                         |  | L3  MLX LLM / VLM      |  |
|  | L2  Tracker + Cache    |  |                         |  | L2  Analytics + Store  |  |
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

### 多模型对比 (RK3588 NPU Core 0, 1080p → 640×640)

| 模型 | 帧数/30s | 检测数 | Person 平均置信度 | Person 范围 | 其他类别 |
|------|----------|--------|-------------------|-------------|----------|
| YOLOv5s (8.5 MB) | 57 | 65 | 71.6% | 51.0–78.9% | book |
| YOLOv5m (21 MB) | 23 | 24 | 90.6% | 89.2–92.7% | bed |
| YOLOv8s (13 MB) | 26 | 26 | 85.0% | 83.2–87.4% | bed, tie, toothbrush |

## 快速开始

### 边缘端 — RK3588 交叉编译

```bash
# 初始化第三方依赖（首次克隆后执行）
git submodule update --init --depth 1

# 组装 sysroot（从 submodule 或本地 RKSDK 提取头文件和库）
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
│   │   ├── ai_inference/          #   RKNN, YOLOv5/v8, 多模型管理/调度
│   │   ├── data_processing/       #   zero-copy buffer, pool, 时序跟踪, 检测缓存
│   │   ├── communication/         #   gRPC client
│   │   └── app/                   #   pipeline coordinator, 自适应帧率, 录制器
│   ├── tests/                     #   GoogleTest (211 tests)
│   └── cmake/                     #   aarch64 toolchain
├── mac-central/                   # 中心端 (Python)
│   ├── src/
│   │   ├── communication/         #   gRPC async server, 限流器
│   │   ├── inference/             #   MLX LLM/VLM, 推理链, RAG 检索
│   │   ├── pipeline/              #   orchestrator, 行为分析, 异常基线
│   │   ├── model_management/      #   模型注册表, A/B 测试
│   │   ├── analytics/             #   时序引擎, 自动标注, ReID, 报告生成
│   │   ├── storage/               #   SQLite, cloud storage
│   │   └── observability/         #   metrics, tracing, alerting
│   └── tests/                     #   pytest (311 tests: 250 unit + 61 e2e/chaos)
├── proto/                         # Protobuf definitions
├── extensions/
│   ├── dashboard/                 # FastAPI + htmx UI
│   └── monitoring/                # Grafana + Prometheus stack
├── third_party/
│   ├── rknn-toolkit2/             # git submodule (RKNN SDK + MPP/RGA)
│   ├── googletest/                # git submodule (v1.14.0)
│   └── stubs/                     # CI 编译用极简 stub 头文件
├── tools/
│   ├── cross_compile_env/         #   Docker + sysroot (构建产物)
│   ├── certs/                     #   mTLS cert gen
│   └── services/                  #   systemd + launchd
├── config.yaml                    # unified config
└── VERSION.json                   # v2.4.0
```

## 测试覆盖

| 组件 | 框架 | 测试数 | 说明 |
|------|------|--------|------|
| C++ 边缘端 (Mock HAL) | GoogleTest | 211 | buffer, pool, HAL, YOLOv5/v8, 多模型, 跟踪器, 自适应帧率 |
| Python 中心端 | pytest | 311 | 限流, 健康检查, 熔断器, 输入校验, 指标, 追踪, 行为分析, RAG |
| 合计 | — | 522+ | 跨编译 mock ON/OFF 均通过 |

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
| v2.0.0 | 智能演进 | 多模型热切换 (YOLOv5/v8)、NPU 三核调度、时序跟踪 v2、动态配置 |
| v2.1.0 | 模型级联 + 仪表板框架 | ModelCascade, V2 API 模块化 |
| v2.2.0 | VLM 引导配置 | VLMConfigGuide, 自动生成配置调整指令 |
| v2.2.1 | Intelligence API 真实数据 | Dashboard 集成真实分析数据 |
| v2.2.2 | C++ 头文件重构 | neuro:: 命名空间统一 |
| v2.3.0 | 生产化增强 | 离线缓存队列、配置热重载、动态日志、Prometheus 告警、SLO 仪表盘、多 VLM 模型 |
| v2.3.1 | 兼容性修复 | GCC aggregate init 修复、摄像头设备路径更新 |
| v2.4.0 | VLM 全链路 | Edge JPEG 帧编码 (stb_image_write)、Central mlx_vlm 修复、VLM 端到端验证 |

## 许可证

[MIT License](LICENSE) — Copyright (c) 2026 Teslavia
