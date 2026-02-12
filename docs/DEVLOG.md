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

## 2026-02-12: Week 1 — 交叉编译工具链 + RK3588 设备部署

### 概述

Week 1 编码任务 (W1-1 ~ W1-7, 101 个测试用例) 已在前一天完成。本日完成两个硬件依赖任务：
1. Docker 交叉编译环境搭建
2. RK3588 设备 SDK 部署与验证

### W1-8: Docker 交叉编译环境

**Objective**: 在 Mac 上通过 Docker 容器编译出 aarch64 可执行文件。

**Implementation**:
- `tools/cross_compile_env/prepare_sysroot.sh` — 从 RKSDK 提取 RKNN/MPP/RGA 头文件+库到 sysroot/
- `tools/cross_compile_env/Dockerfile` — debian:bookworm + aarch64-linux-gnu 工具链
- `tools/cross_compile_env/build_rk3588.sh` — Docker 自动化：外部自动 build image + run，内部执行 cmake + make
- `rk3588-edge/cmake/aarch64-toolchain.cmake` — 重构 sysroot 逻辑
- `rk3588-edge/CMakeLists.txt` — 交叉编译 protobuf/gRPC 发现修复

**Challenges & Solutions**:

| # | 问题 | 根因 | 解决方案 |
|---|---|---|---|
| 1 | MPP `librockchip_mpp.so` 复制失败 | macOS 上 git 无法正确还原 ELF 格式的 symlink target，`.so` 和 `.so.1` 是 broken symlinks | 从 `.so.0` (真实 ELF) 复制，手动创建 `.so` → `.so.0` 符号链接 |
| 2 | `docker pull ubuntu:22.04` 失败 (content size of zero) | Docker Desktop 本地 containerd manifest 缓存损坏 | 切换基础镜像为 `debian:bookworm`（同为 Debian 系，包完全兼容） |
| 3 | Docker build context xattr 错误 | macOS `._` 扩展属性文件导致 Docker buildx 的 xattr 操作失败 | 构建前执行 `dot_clean` 清理 |
| 4 | `find_package(Protobuf)` 在交叉编译时失败 | `CMAKE_SYSROOT` 设置后 `CMAKE_FIND_ROOT_PATH_MODE_*=ONLY` 限制了搜索范围 | 初版：用 `NO_CMAKE_FIND_ROOT_PATH` 绕过。最终版：不设 CMAKE_SYSROOT |
| 5 | `features.h: No such file or directory` | 我们的 sysroot 只有 RKNN/MPP/RGA 库，没有完整 libc headers，但 `CMAKE_SYSROOT` 让编译器只在 sysroot 里找 | 彻底移除 `CMAKE_SYSROOT`，改用 `include_directories(SYSTEM ...)` + `link_directories()` 添加 SDK 路径 |
| 6 | `.dockerignore` 排除了 sysroot 中的 `.so` 文件 | `**/*.so` 规则过于宽泛，`!sysroot/` 只保留目录不保留内容 | 从 `.dockerignore` 移除 `**/*.so` 和 `**/*.a` |
| 7 | CMakeLists.txt `endif()` 嵌套错误 | 编辑 gRPC 查找逻辑时遗留了多余的 `endif()` | 修正 if/else/endif 嵌套结构 |
| 8 | `find_library(rknnrt)` 在 Docker 内找不到 | 库在 `/opt/rk3588-sysroot/usr/lib` 但 `find_library` 只搜索 `/usr/lib` | 在 `PATHS` 中添加 `/opt/rk3588-sysroot/usr/lib` |

**Key Architectural Decision**:

> **不使用 CMAKE_SYSROOT 做部分 sysroot**
>
> 标准交叉编译流程中 `CMAKE_SYSROOT` 指向一个完整的 target rootfs（包含 libc、libstdc++ 等）。
> 我们的 sysroot 只包含 RKNN/MPP/RGA 三个 vendor 库，设置 `CMAKE_SYSROOT` 会导致编译器
> 丢失 cross-compiler 自带的 system headers。正确做法是保持编译器默认搜索路径不变，
> 仅通过 `include_directories(SYSTEM ...)` 和 `link_directories()` 追加 vendor SDK 路径。

**Result**: 256K aarch64 ELF 可执行文件，`USE_MOCK_HAL=ON` 和 `OFF` 两种模式均编译通过。

### W1-9: RK3588 设备 SDK 部署

**Objective**: 通过 SSH 部署 SDK 到 Radxa ROCK 5B Plus，验证 NPU 可用性。

**Implementation**:
- `tools/rk3588_device.conf` — 设备连接配置
- `tools/deploy_rk3588.sh` — 6 步 SDK 部署脚本
- `tools/deploy_and_run.sh` — 编译→部署→运行一体化脚本

**Challenges & Solutions**:

| # | 问题 | 根因 | 解决方案 |
|---|---|---|---|
| 1 | SSH 密钥认证失败 | 设备未配置 Mac 的公钥 | `sshpass` + `ssh-copy-id` 推送 ed25519 公钥 |
| 2 | NPU 驱动检测失败 (dmesg permission denied) | 非 root 用户无法读取 debugfs | 改用 `sudo cat /sys/kernel/debug/rknpu/version` |
| 3 | `rknn_server` 部署失败 (Text file busy) | 设备上 rknn_server 进程正在运行 | 部署前先 `sudo killall rknn_server` |
| 4 | `ldconfig -p` 验证失败 (command not found) | 非 root 用户 PATH 中没有 `/sbin` | 改用 `sudo ldconfig -p` |
| 5 | sudo 需要密码导致脚本中断 | 设备默认需要交互式密码输入 | 配置 `/etc/sudoers.d/rock` NOPASSWD |

**Device Verification Results**:

```
Board:      Radxa ROCK 5B Plus
Kernel:     Linux 6.1.84-8-rk2410 aarch64
CPU:        8 cores (4x Cortex-A76 + 4x Cortex-A55)
RAM:        16GB
Storage:    63GB NVMe
NPU:        RKNPU driver v0.9.8, 3 cores (Core0/1/2: 0% idle)
Libraries:  librknnrt.so ✓  librockchip_mpp.so ✓  librga.so ✓
Binary:     neuro_pipeline_edge runs successfully (pipeline stub)
```

### Sysroot 组装结果

```
sysroot/usr/include/
  rknn_api.h, rknn_matmul_api.h, rknn_custom_op.h     (RKNN: 3 files)
  rockchip/*.h                                          (MPP: 23 files)
  rga/*.h, *.hpp                                        (RGA: 18 files)
sysroot/usr/lib/
  librknnrt.so                                          (RKNN runtime)
  librockchip_mpp.so → .so.0                            (MPP, symlink fixed)
  librga.so, librga.a                                   (RGA)
Total: 37MB
```

### 版本发布

- `VERSION.json` — v0.1.0
- Git tag: `v0.1.0`
- Branch: `milestone/week1-foundation` → merged to `main`

---

## 2026-02-12: Week 1 复盘 (Retrospective)

### 完成度评估

| 计划任务 | 状态 | 测试覆盖 |
|---|---|---|
| W1-1: mmap IPC 共享内存 | ✅ | 9 tests |
| W1-2: MemoryPool 物理/虚拟地址 | ✅ | 14 tests |
| W1-3: NPU 多核任务调度器 | ✅ | 16 tests |
| W1-4: CPU 缓存优化分析 | ✅ | 12 tests |
| W1-5: ARM NEON 图像操作 | ✅ | 14 tests |
| W1-6: DMA-BUF 共享模拟 | ✅ | 12 tests |
| W1-7: 虚拟设备文件 I/O | ✅ | 14 tests |
| W1-8: Docker 交叉编译环境 | ✅ | 手动验证 |
| W1-9: RK3588 设备 SDK 部署 | ✅ | 手动验证 |
| **Total** | **9/9 (100%)** | **101 unit tests** |

### 做得好的

1. **TDD 严格执行** — 每个模块先写测试再实现，101 个测试用例全部通过
2. **Mock HAL 设计** — `USE_MOCK_HAL` 开关让开发和真实部署无缝切换
3. **文档体系** — ARCHITECTURE.md, API_REFERENCE.md, 9 份技术笔记
4. **问题追踪** — 每个 bug 都有根因分析和解决方案记录

### 需要改进的

1. **CI/CD 不完整** — 现有 CI 只覆盖 Python 测试和 proto 验证，缺少 C++ 交叉编译验证
2. **DEVLOG 滞后** — 交叉编译和设备部署的工作没有实时记录，事后补写
3. **README Quick Start 过时** — 没有反映 Docker 工作流和设备部署流程
4. **集成测试缺失** — 只有单元测试，没有端到端集成测试
5. **错误处理不够健壮** — 部署脚本遇到 sudo/ldconfig 问题时直接失败，缺少优雅降级

### 关键经验 (Lessons Learned)

1. **macOS + Docker + 交叉编译 = 三重陷阱** — `._ 文件`、`symlink 语义差异`、`Docker Desktop 缓存损坏` 三个平台差异问题叠加
2. **部分 sysroot 不能用 CMAKE_SYSROOT** — 这是一个容易踩的坑，文档中很少提及
3. **设备部署脚本必须假设最差环境** — sudo 需要密码、服务正在运行、PATH 不完整
4. **`.dockerignore` 的排除规则是全局的** — `!dir/` 只保留目录，不覆盖内容级别的排除规则

### 优化点 (Action Items for Week 2)

- [ ] CI 增加 Docker 交叉编译 job
- [ ] 增加 C++ 单元测试在 Docker 内运行的 CI job
- [ ] README 更新 Docker 工作流
- [ ] 考虑 Makefile 或 justfile 统一常用命令入口

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
