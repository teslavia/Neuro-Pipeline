# Neuro-Pipeline Development Log

**Purpose**: 记录所有架构决策、实现细节、调试过程和优化经验。

---

## 2026-02-11: Phase 1 — 项目初始化

### 环境搭建

**仓库创建**:
- Location: `/Volumes/TMAC/Satoshi/DEV/mac/TTest/RKPRO/repo`
- 初始状态: 仅有中文架构设计文档

**版本控制**:
- 初始化 Git 仓库
- 创建 `.gitignore` 覆盖: C/C++ 构建产物、Python 字节码、大模型文件、IDE 配置、OS 文件

**配置文件**:
- `.editorconfig` — 统一格式（C++ 2空格, Python 4空格, LF 换行）
- `.clang-format` — 基于 Google Style，自定义 include 排序
- `pyproject.toml` — Black, Flake8, pytest, mypy 集成配置

### 架构决策

**目录结构**:
- 边缘侧 (C++) 和中心侧 (Python) 工具链不同，物理隔离
- `include/` 目录促进 header-only 接口设计，清晰 API 边界
- `generated/` 隔离 Protobuf 生成代码与手写代码
- 测试并行结构: `unit_tests/` + `integration_tests/`

**构建系统**:
- Edge: CMake (C++ 交叉编译行业标准)
- Central: setuptools (Python 标准, pip 集成)
- Protobuf 生成: `tools/generate_proto.py` 脚本保证可复现性

**技术栈决策**:

| Decision | Rationale |
|---|---|
| C++17 for Edge | 现代特性 (std::optional, variant) 与 RK3588 工具链兼容的平衡 |
| Python 3.10+ for Central | MLX 要求 3.10+, walrus operator, pattern matching |
| gRPC over WebSocket | 更好的流控, HTTP/2 多路复用, Protobuf 原生集成 |
| GoogleTest over Catch2 | CMake 集成更佳, 行业标准 |
| pytest over unittest | 更 Pythonic, fixture 系统更强大 |

### 关键挑战识别

1. **交叉编译复杂性** — 需要 Docker 容器 + aarch64 工具链 + RK3588 特有库
2. **零拷贝内存管理** — DMA-BUF 生命周期跟踪，多消费者共享
3. **Protobuf Schema 演进** — 边缘/中心必须同步，破坏性变更风险

### GitHub 参考仓库调研

完成了以下维度的 GitHub 项目调研:
- RK3588 NPU 推理部署 (airockchip/rknpu2, rknn_model_zoo)
- Rockchip 平台工具链 (rockchip-linux org, ffmpeg-rockchip)
- Apple Silicon MLX 推理 (ml-explore/mlx, vllm-mlx)
- 边缘-云协同架构 (ScorcaF/Edge-Cloud-Collaborative-Inference)
- gRPC 视频流传输 (isthisdan/grpc-video-streaming)

### Next Steps (Week 1)

- [ ] 实现 mmap IPC 共享内存示例
- [ ] 实现简单内存池 (物理/虚拟地址模拟)
- [ ] 设计 V4L2/RGA C++ Wrapper
- [ ] 实现 C++ 线程池
- [ ] 模拟 NPU 任务调度
- [ ] CPU 缓存优化分析
- [ ] ARM NEON 图像操作
- [ ] 搭建交叉编译工具链

---

## Entry Template

### YYYY-MM-DD: [Task/Feature Name]

**Objective**: [目标描述]

**Implementation**:
- [关键代码变更]
- [修改文件列表]

**Challenges**:
- [问题描述]
- [根因分析]
- [解决方案]

**Testing**:
- [编写的测试用例]
- [测试结果]

**Performance**:
- [基准测试 (如适用)]
- [优化笔记]

**References**:
- [文档链接]

**Learnings**:
- [关键收获]
