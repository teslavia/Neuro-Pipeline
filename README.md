# Neuro-Pipeline

**跨异构硬件平台的智能感知与推理系统**

[![CI](https://github.com/teslavia/neuro-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/teslavia/neuro-pipeline/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Overview

Neuro-Pipeline 是一个生产级 AI 推理系统，实现 **RK3588 嵌入式边缘设备** 与 **Apple Silicon Mac Mini** 之间的高效协同：

- **RK3588 边缘侧** — 实时视频采集、零拷贝处理管线（V4L2/MPP/RGA/DMA-BUF）、RKNN NPU 推理（YOLO 系列）
- **Mac Mini 中心侧** — MLX 框架驱动的 LLM/VLM 大模型推理、Prompt Engineering、事件编排
- **gRPC 通信** — 基于 HTTP/2 的高性能双向流式通信，Protobuf 序列化

## Architecture

```
┌─────────────────────────┐         gRPC / Protobuf          ┌─────────────────────────┐
│   RK3588 Edge Device    │ ◄──────────────────────────────► │    Mac Mini Central     │
│  (Embedded Linux / C++) │   Detection Results, Frames      │  (macOS / Python / MLX) │
│                         │   Control Commands, Events       │                         │
│  Layer 5: App Logic     │                                  │  Layer 5: Orchestration │
│  Layer 4: gRPC Client   │                                  │  Layer 4: gRPC Server   │
│  Layer 3: RKNN NPU      │                                  │  Layer 3: MLX VLM/LLM   │
│  Layer 2: Zero-Copy Buf │                                  │  Layer 2: Data Format   │
│  Layer 1: V4L2/MPP/RGA  │                                  │  Layer 1: Apple Silicon │
└─────────────────────────┘                                  └─────────────────────────┘
```

### Zero-Copy Data Flow (RK3588)

```
V4L2 Camera ──► MPP Decoder ──► RGA Processor ──► RKNN NPU
    │                │                │                │
    └────────────────┴────────────────┴────────────────┘
              DMA-BUF File Descriptor Passing
             (Zero Memory Copy Between HW Units)
```

## Project Status

**Current Version**: v0.3.5 (Week 3 Complete + P1/P2 Fixes)

### Week 3 Achievements ✅
- ✅ gRPC C++ client with persistent streaming + bidirectional event stream
- ✅ gRPC Python async server with keepalive, compression, 16MB message limit
- ✅ MLX inference engine (stub + real mode) on Apple Silicon
- ✅ Pipeline coordinator integrated with gRPC + health updates
- ✅ Bidirectional control commands (SET_FPS, SET_THRESHOLD, SHUTDOWN)

### P1/P2 Defect Fixes (v0.3.5) ✅
- ✅ Unified config system (config.yaml + C++/Python loaders)
- ✅ Structured logging (C++ LOG macros + Python structlog)
- ✅ Error handling (C++ ErrorCode/Result<T> + Python exception hierarchy)
- ✅ VLM trigger rules configurable (replacing hardcoded logic)
- ✅ Memory pool alignment + stats, thread pool queue limits
- ✅ CI: native C++ test job + Python E2E integration tests
- ✅ Proto: trace_id, ErrorReport, CONTROL_COMMAND event type

### Week 2 Achievements ✅
- ✅ HAL Layer: V4L2, MPP, RGA, DRM/DMA-BUF real implementation
- ✅ AI Inference: RKNN NPU engine + YOLO postprocessor (NCHW fixed)
- ✅ Zero-Copy Pipeline: DMA-BUF fd sharing across hardware units
- ✅ Performance: 28.5 FPS @ 1080p, 20.3ms latency, 72% NPU utilization

---

## Quick Start

### Prerequisites

**RK3588 Edge:**
- RK3588 开发板（Orange Pi 5 Plus / Radxa ROCK 5B 等）
- 交叉编译工具链 `aarch64-linux-gnu-gcc 11+`
- CMake 3.20+
- RKNN SDK 2.0+, MPP, RGA 库

**Mac Mini Central:**
- macOS 13+（Apple Silicon M1/M2/M3/M4）
- Python 3.10+
- MLX 框架

### Build RK3588 Edge (Docker — Recommended)

```bash
# 1. 组装 sysroot（从本地 RKSDK 提取头文件和库）
bash tools/cross_compile_env/prepare_sysroot.sh

# 2. Docker 内交叉编译（自动构建镜像 + 编译）
USE_MOCK_HAL=ON bash tools/cross_compile_env/build_rk3588.sh

# 3. 验证生成的 aarch64 二进制
file rk3588-edge/build/neuro_pipeline_edge
# → ELF 64-bit LSB pie executable, ARM aarch64
```

环境变量:
- `USE_MOCK_HAL=ON` — 无需真实 SDK，用于开发验证（默认）
- `USE_MOCK_HAL=OFF` — 链接真实 RKNN/MPP/RGA 库
- `BUILD_TYPE=Release|Debug` — 构建类型（默认 Release）

### Deploy to RK3588 Device

```bash
# 部署 SDK 库到设备（librknnrt, MPP, RGA）
bash tools/deploy_rk3588.sh

# 一键：编译 → 部署 → 远程运行
bash tools/deploy_and_run.sh
```

### Build RK3588 Edge (Native — Without Docker)

```bash
# 需要本地安装 aarch64-linux-gnu-gcc
cd rk3588-edge
mkdir build && cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake/aarch64-toolchain.cmake
make -j$(nproc)
```

### Setup Mac Central

```bash
cd mac-central
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 生成 Protobuf 代码
cd .. && python3 tools/generate_proto.py

# 启动中心服务器
cd mac-central && python main.py --port 50051
```

### Docker Cross-Compilation (Alternative)

```bash
# 如果需要手动控制 Docker 流程
cd tools/cross_compile_env
docker build -t neuro-pipeline-builder .
docker run -v $(pwd)/../..:/workspace -e USE_MOCK_HAL=ON -e IN_DOCKER=1 \
  neuro-pipeline-builder bash /workspace/tools/cross_compile_env/build_rk3588.sh
```

## Directory Structure

```
neuro-pipeline/
├── docs/                          # 项目文档
│   ├── ARCHITECTURE.md            # 详细架构设计
│   ├── API_REFERENCE.md           # gRPC API 参考
│   └── DEVLOG.md                  # 开发日志
├── proto/                         # Protobuf 定义
│   └── neuro_pipeline.proto       # 核心消息与服务定义
├── rk3588-edge/                   # RK3588 边缘侧 (C/C++)
│   ├── include/                   # 公共头文件
│   │   ├── rk_hal/                #   HAL 层接口
│   │   └── common/                #   通用数据结构
│   ├── src/
│   │   ├── hal/                   # 硬件抽象 (V4L2, MPP, RGA, DRM)
│   │   ├── ai_inference/          # RKNN 推理引擎
│   │   ├── data_processing/       # 零拷贝缓冲区管理
│   │   ├── communication/         # gRPC 客户端
│   │   └── app/                   # 主应用逻辑
│   ├── tests/                     # GoogleTest 测试
│   ├── models/                    # .rknn 模型文件
│   └── CMakeLists.txt             # CMake 构建配置
├── mac-central/                   # Mac Mini 中心侧 (Python)
│   ├── src/
│   │   ├── communication/         # gRPC 服务器
│   │   ├── llm_vlm/               # MLX 推理, Prompt Engineering
│   │   └── application_logic/     # 事件编排, 业务逻辑
│   ├── tests/                     # pytest 测试
│   ├── models/                    # MLX 格式大模型
│   ├── requirements.txt           # Python 依赖
│   └── main.py                    # 入口程序
├── tools/                         # 工具与脚本
│   ├── cross_compile_env/         # Docker 交叉编译环境
│   │   ├── Dockerfile             #   debian:bookworm + aarch64 toolchain
│   │   ├── build_rk3588.sh        #   自动化编译脚本
│   │   └── prepare_sysroot.sh     #   RKSDK sysroot 组装
│   ├── deploy_rk3588.sh           # RK3588 SDK 部署
│   ├── deploy_and_run.sh          # 编译→部署→运行一体化
│   ├── rk3588_device.conf         # 设备连接配置
│   ├── rknn_toolkit_scripts/      # 模型转换, 量化脚本
│   └── generate_proto.py          # Protobuf 代码生成
├── VERSION.json                   # 版本号文件
└── extensions/                    # 拓展任务隔离区
```

## Development Workflow

1. **Protobuf 变更** — 修改 `proto/neuro_pipeline.proto` → 运行 `python3 tools/generate_proto.py`
2. **边缘侧开发** — TDD (GoogleTest) → 交叉编译 → 部署至 RK3588
3. **中心侧开发** — TDD (pytest) → 本地运行 Mac Mini
4. **集成测试** — 双端联调，端到端验证

## Technology Stack

| Component | RK3588 Edge | Mac Mini Central |
|---|---|---|
| **Language** | C++17 | Python 3.10+ |
| **Build** | CMake 3.20+ | setuptools / pip |
| **Video** | V4L2 + MPP (HW) | — |
| **Image Processing** | RGA (HW) | OpenCV / Pillow |
| **AI Framework** | RKNN NPU (6 TOPS) | MLX (Apple Silicon) |
| **Model Format** | .rknn (INT8) | MLX quantized (4-bit) |
| **Communication** | gRPC C++ | gRPC Python |
| **Serialization** | Protobuf 3 | Protobuf 3 |
| **Testing** | GoogleTest | pytest |

## Documentation

- [Architecture Design](docs/ARCHITECTURE.md) — 分层架构、数据流、设计决策
- [API Reference](docs/API_REFERENCE.md) — gRPC 服务接口 + HAL 层 API
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) — 交叉编译、设备部署、运行指南
- [Troubleshooting](docs/TROUBLESHOOTING.md) — 常见问题排查
- [Technical Decisions](docs/TECHNICAL_DECISIONS.md) — 架构决策记录 (TD-001 ~ TD-007)

## Performance Targets

| Metric | Target |
|---|---|
| Edge Inference Latency | < 20ms (YOLO on NPU) |
| Video Frame Rate | 30 FPS (1080p) |
| Network Round-Trip | < 100ms |
| Central VLM Inference | < 2s (quantized) |
| Edge Memory Footprint | < 512MB |

## License

[MIT License](LICENSE) - Copyright (c) 2026 Teslavia
