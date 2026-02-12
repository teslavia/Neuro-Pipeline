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

- [x] 实现 mmap IPC 共享内存示例
- [x] 实现简单内存池 (物理/虚拟地址模拟)
- [x] 模拟 NPU 任务调度
- [x] CPU 缓存优化分析
- [x] ARM NEON 图像操作
- [x] DMA-BUF 共享模拟
- [x] 虚拟设备文件 I/O
- [x] Week 1 技术文档笔记
- [ ] 搭建交叉编译工具链 (需要 Docker 环境)
- [ ] RK3588 设备 SDK 部署

---

## 2026-02-11: Week 1 — 基础模块实现

### W1-1: mmap IPC 共享内存

**Objective**: 实现 POSIX 共享内存 IPC，为进程间零拷贝通信打基础。

**Implementation**:
- `include/common/mmap_ipc.hpp` — MmapSharedMemory 类 (Create/Open 模式)
- `src/data_processing/mmap_ipc.cpp` — 基于 shm_open + mmap 的完整实现
- 支持 Write/Read 带偏移量、边界保护、Move 语义

**Testing**: 9 个测试用例
- CreateAndValidate, WriteAndReadBack, WriteAtOffset
- BoundaryProtection, ReadBeyondSize, CreatorConsumerSharing
- DirectMemoryAccess, MoveSemantics, ConcurrentReadWrite

### W1-2: MemoryPool 物理/虚拟地址模拟

**Objective**: 增强内存池，模拟 CMA 区域的物理/虚拟地址映射。

**Implementation**:
- 构造函数新增 `phys_base_addr` 参数 (默认 0x10000000)
- 新增: VirtToPhys, PhysToVirt, ContainsVirt, ContainsPhys
- PhysBaseAddr, PhysEndAddr 访问器

**Testing**: 14 个新测试用例
- PhysBaseAddr 默认/自定义、ContainsVirt/Phys 边界
- VirtToPhys 往返转换、连续块对齐验证
- 无效地址处理、内部偏移量转换
- 跨地址域数据完整性 (WriteViaVirtReadViaPhys)

### W1-3: NPU 多核任务调度器

**Objective**: 完善 RK3588 三核 NPU 调度模型，支持多策略负载均衡。

**Implementation**:
- `include/common/npu_scheduler.hpp` — 完整头文件，线程安全
- 4 种策略: RoundRobin, LoadBalance, SingleCore, TripleCore
- 活跃任务计数 (NotifyTaskStart/End)，运行时策略切换
- 原子计数器 + mutex 保证线程安全

**Testing**: 16 个测试用例
- 每种策略的正确性验证
- 负载均衡: 最少负载选择、任务结束后更新、平局处理
- 任务跟踪: 递增/递减、无效索引保护
- 并发安全: 多线程 SelectCore + 多线程 LoadBalance

### W1-4: CPU 缓存优化分析

**Objective**: 对比 cache-friendly vs cache-unfriendly 内存访问模式。

**Implementation**:
- `include/common/cache_analysis.hpp` + `src/data_processing/cache_analysis.cpp`
- SumRowMajor (顺序) vs SumColumnMajor (跳跃) 矩阵遍历
- SumSequential vs SumStrided 数组访问
- BenchmarkMatrixTraversal / BenchmarkStridedAccess 计时接口

**Testing**: 12 个测试用例 — 正确性 + 基准集成测试

### W1-5: ARM NEON 图像操作

**Objective**: 实现 SIMD 加速图像处理原语 (带标量回退)。

**Implementation**:
- `include/common/neon_image_ops.hpp` + `src/data_processing/neon_image_ops.cpp`
- RgbToBgr — 通道交换 (NEON: vld3q/vst3q)
- RgbaToRgb — Alpha 通道剥离 (NEON: vld4q/vst3q)
- NormalizeRgb — ImageNet 风格均值减除+缩放
- AbsDiff — 帧差检测
- Clamp — 范围限制

**Testing**: 14 个测试用例 — 正确性、往返验证、大缓冲区、空指针安全

### W1-6: DMA-BUF 共享模拟

**Objective**: 模拟 DMA-BUF fd 机制，用于无硬件环境开发。

**Implementation**:
- `include/rk_hal/dmabuf_sim.hpp` + `src/hal/dmabuf_sim.cpp`
- Allocate/Free — 模拟 CMA 分配，页对齐物理地址
- Export/Import — 模拟跨进程 fd 共享
- Mmap — 虚拟地址映射
- BufferInfo — 元数据查询

**Testing**: 12 个测试用例 — 分配/释放、Mmap 写入、Export/Import 共享、物理地址页对齐

### W1-7: 虚拟设备文件 I/O

**Objective**: 模拟 Linux 设备文件操作 (/dev/*, /sys/*)。

**Implementation**:
- `include/common/virtual_device_io.hpp` + `src/data_processing/virtual_device_io.cpp`
- RegisterDevice — 注册虚拟设备
- Open/Close/Read/Write — 标准文件操作语义
- Ioctl — 自定义请求处理器注册
- 支持多设备独立操作

**Testing**: 14 个测试用例 — 注册、Open/Close、Read 部分+EOF、Write 追加、Ioctl 处理、多设备独立

### 架构决策

| Decision | Rationale |
|---|---|
| NPU 调度器独立头文件 | 从内联 .cpp 提取为 .hpp + .cpp，支持测试和复用 |
| NEON 条件编译 | `#if USE_NEON` 保证 Mac 开发 + ARM64 部署双平台兼容 |
| DmaBufSim 页对齐 | 模拟真实 CMA 4KB 页对齐行为 |
| VirtualDeviceIO ioctl handler | std::function 回调允许测试注入任意 ioctl 行为 |

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
