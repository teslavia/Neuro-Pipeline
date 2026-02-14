# Neuro-Pipeline 故障排查指南 (Troubleshooting Guide)

**版本**: v1.1.0
**更新日期**: 2026-02-14

---

## 一、交叉编译问题

### 1.1 Docker 构建失败

**症状**:
```
ERROR: failed to solve: process "/bin/sh -c apt-get update" did not complete successfully
```

**原因**: Docker 网络不稳定或 apt 源不可达

**解决方案**:
```bash
# 使用国内镜像源
docker build --build-arg APT_MIRROR=mirrors.tuna.tsinghua.edu.cn -t neuro-pipeline-builder .
```

---

### 1.2 Sysroot 库文件缺失

**症状**:
```
/usr/bin/ld: cannot find -lrknnrt
```

**原因**: `prepare_sysroot.sh` 未正确提取 SDK 库

**解决方案**:
```bash
# 检查 RKSDK 路径
echo $RKSDK_PATH
# 应输出: /Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK

# 重新生成 sysroot
rm -rf tools/cross_compile_env/sysroot
bash tools/cross_compile_env/prepare_sysroot.sh

# 验证库文件
ls -lh tools/cross_compile_env/sysroot/lib/*.so*
```

---

### 1.3 macOS 符号链接问题

**症状**:
```
librockchip_mpp.so: No such file or directory
```

**原因**: macOS git 无法正确处理 Linux 符号链接

**解决方案**:
```bash
# 在 Docker 内手动创建符号链接
cd tools/cross_compile_env/sysroot/lib
ln -sf librockchip_mpp.so.0 librockchip_mpp.so
ln -sf librga.so.2 librga.so
```

---

### 1.4 CMake 找不到工具链

**症状**:
```
CMake Error: CMAKE_CXX_COMPILER not set
```

**原因**: 工具链文件路径错误

**解决方案**:
```bash
# 使用绝对路径
cmake .. -DCMAKE_TOOLCHAIN_FILE=$(pwd)/../cmake/aarch64-toolchain.cmake
```

---

## 二、RK3588 设备问题

### 2.1 SSH 连接失败

**症状**:
```
ssh: connect to host 192.168.1.70 port 22: Connection refused
```

**原因**: 设备未启动或 IP 地址变更

**解决方案**:
```bash
# 扫描局域网设备
nmap -sn 192.168.1.0/24 | grep -B 2 "Radxa"

# 或通过路由器管理界面查看设备 IP

# 更新 tools/rk3588_device.conf
DEVICE_HOST="新IP地址"
```

---

### 2.2 权限不足

**症状**:
```
Permission denied (publickey)
```

**原因**: SSH 密钥未配置

**解决方案**:
```bash
# 生成 SSH 密钥
ssh-keygen -t ed25519 -f ~/.ssh/rk3588_key

# 上传公钥到设备
ssh-copy-id -i ~/.ssh/rk3588_key.pub rock@192.168.1.70

# 配置 ~/.ssh/config
cat >> ~/.ssh/config <<EOF
Host rk3588
  HostName 192.168.1.70
  User rock
  IdentityFile ~/.ssh/rk3588_key
EOF
```

---

### 2.3 库文件找不到

**症状**:
```
./neuro_pipeline_edge: error while loading shared libraries: librknnrt.so: cannot open shared object file
```

**原因**: `LD_LIBRARY_PATH` 未设置

**解决方案**:
```bash
# 临时设置
export LD_LIBRARY_PATH=/opt/neuro-pipeline/lib:$LD_LIBRARY_PATH

# 永久设置
echo 'export LD_LIBRARY_PATH=/opt/neuro-pipeline/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# 或使用 ldconfig
sudo bash -c 'echo "/opt/neuro-pipeline/lib" > /etc/ld.so.conf.d/neuro-pipeline.conf'
sudo ldconfig
```

---

### 2.4 V4L2 设备打开失败

**症状**:
```
[ERROR] Failed to open /dev/video0: No such file or directory
```

**原因**: 摄像头未连接或设备节点错误

**解决方案**:
```bash
# 列出所有 V4L2 设备
v4l2-ctl --list-devices

# 测试摄像头
v4l2-ctl -d /dev/video0 --all

# 如果是 USB 摄像头，检查 dmesg
dmesg | grep -i video

# 使用正确的设备节点
./neuro_pipeline_edge --device /dev/video1
```

---

### 2.5 NPU 推理失败

**症状**:
```
[ERROR] rknn_init failed: RKNN_ERR_MODEL_INVALID
```

**原因**: 模型文件损坏或版本不匹配

**解决方案**:
```bash
# 验证模型文件
file models/yolov5s-640-640.rknn
# 应输出: data

# 检查 RKNN 版本
cat /sys/kernel/debug/rknpu/version
# 应输出: 0.9.8 或更高

# 重新下载模型
rm models/yolov5s-640-640.rknn
bash tools/download_model.sh

# 或使用 rknn_benchmark 验证
cd /opt/neuro-pipeline
rknn_benchmark models/yolov5s-640-640.rknn
```

---

### 2.6 DMA-BUF 分配失败

**症状**:
```
[ERROR] DRM_IOCTL_MODE_CREATE_DUMB failed: Cannot allocate memory
```

**原因**: CMA 内存不足

**解决方案**:
```bash
# 检查 CMA 内存
cat /proc/meminfo | grep Cma
# CmaTotal: 512000 kB
# CmaFree: 123456 kB

# 如果 CmaFree 过低，重启设备
sudo reboot

# 或调整 CMA 大小（需重启）
sudo nano /boot/extlinux/extlinux.conf
# 添加: cma=512M
```

---

## 三、Mac Mini 中心侧问题

### 3.1 MLX 安装失败

**症状**:
```
ERROR: Could not find a version that satisfies the requirement mlx
```

**原因**: 非 Apple Silicon 平台或 Python 版本过低

**解决方案**:
```bash
# 检查架构
uname -m
# 应输出: arm64

# 检查 Python 版本
python3 --version
# 应 >= 3.10

# 使用正确的 Python
python3.10 -m venv venv
source venv/bin/activate
pip install mlx mlx-lm
```

---

### 3.2 gRPC 服务器启动失败

**症状**:
```
[ERROR] Address already in use: 0.0.0.0:50051
```

**原因**: 端口被占用

**解决方案**:
```bash
# 查找占用进程
lsof -i :50051

# 杀死进程
kill -9 <PID>

# 或使用其他端口
python main.py --port 50052
```

---

### 3.3 Protobuf 版本不匹配

**症状**:
```
TypeError: Descriptors cannot not be created directly
```

**原因**: protobuf 版本冲突

**解决方案**:
```bash
# 卸载旧版本
pip uninstall protobuf

# 安装兼容版本
pip install protobuf==3.20.3

# 重新生成代码
python3 tools/generate_proto.py
```

---

### 3.4 MLX 模型加载失败

**症状**:
```
[ERROR] Model not found: models/qwen2-vl-2b
```

**原因**: 模型未下载

**解决方案**:
```bash
# 手动下载
cd mac-central
huggingface-cli download mlx-community/Qwen2-VL-2B-Instruct \
  --local-dir models/qwen2-vl-2b

# 或使用脚本
bash scripts/download_models.sh
```

---

## 四、通信问题

### 4.1 gRPC 连接超时

**症状**:
```
[ERROR] failed to connect to all addresses: deadline exceeded
```

**原因**: 网络不通或防火墙阻止

**解决方案**:
```bash
# 测试网络连通性
ping 192.168.1.100

# 测试端口
nc -zv 192.168.1.100 50051

# 检查防火墙（Mac Mini）
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 临时关闭防火墙测试
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```

---

### 4.2 Protobuf 反序列化失败

**症状**:
```
[ERROR] Failed to parse DetectionResult
```

**原因**: C++ 和 Python 使用不同版本的 .proto

**解决方案**:
```bash
# 确保两端使用相同的 proto 文件
diff rk3588-edge/src/generated/neuro_pipeline.pb.h \
     mac-central/src/generated/neuro_pipeline_pb2.py

# 重新生成代码
python3 tools/generate_proto.py

# 重新编译 C++ 端
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh
```

---

### 4.3 视频流传输卡顿

**症状**: 边缘侧 FPS 正常，但中心侧接收延迟高

**原因**: 网络带宽不足或 JPEG 压缩质量过高

**解决方案**:
```bash
# 降低 JPEG 质量
./neuro_pipeline_edge --jpeg-quality 70

# 降低分辨率
./neuro_pipeline_edge --width 640 --height 480

# 减少上传频率
./neuro_pipeline_edge --upload-interval 5
```

---

## 五、性能问题

### 5.1 FPS 过低

**症状**: 端到端 FPS < 15

**诊断**:
```bash
# 查看各阶段延迟
./neuro_pipeline_edge --log-level debug | grep "Latency"

# 检查 NPU 利用率
cat /sys/kernel/debug/rknpu/load

# 检查 CPU 占用
top -p $(pgrep neuro_pipeline)
```

**解决方案**:
- V4L2 采集慢 → 降低分辨率或帧率
- MPP 解码慢 → 检查视频编码格式
- RKNN 推理慢 → 使用更小的模型或 INT8 量化
- YOLO 后处理慢 → 调高置信度阈值减少检测框

---

### 5.2 内存泄漏

**症状**: 运行一段时间后内存占用持续增长

**诊断**:
```bash
# 监控内存
watch -n 1 'ps aux | grep neuro_pipeline'

# 使用 valgrind（需在设备上编译 Debug 版本）
valgrind --leak-check=full ./neuro_pipeline_edge
```

**解决方案**:
- 检查 DMA-BUF fd 是否正确释放
- 检查 RKNN context 是否正确销毁
- 检查 shared_ptr 循环引用

---

### 5.3 NPU 利用率低

**症状**: NPU 利用率 < 50%

**原因**: 数据准备成为瓶颈

**解决方案**:
```bash
# 启用多核 NPU
./neuro_pipeline_edge --npu-cores 3

# 使用零拷贝路径
# 确保编译时 USE_MOCK_HAL=OFF

# 预分配 buffer pool
# 在 pipeline_coordinator.cpp 中增加 buffer pool 大小
```

---

## 六、调试技巧

### 6.1 启用详细日志

```bash
# 边缘侧
./neuro_pipeline_edge --log-level debug

# 中心侧
python main.py --log-level DEBUG
```

---

### 6.2 单步调试

```bash
# 使用 gdb（需 Debug 版本）
gdb ./neuro_pipeline_edge
(gdb) break pipeline_coordinator.cpp:123
(gdb) run
(gdb) print frame.size
```

---

### 6.3 性能分析

```bash
# 使用 perf
perf record -g ./neuro_pipeline_edge
perf report

# 使用 rknn_benchmark
rknn_benchmark models/yolov5s-640-640.rknn
```

---

### 6.4 网络抓包

```bash
# 抓取 gRPC 流量
sudo tcpdump -i any -w grpc.pcap port 50051

# 使用 Wireshark 分析
wireshark grpc.pcap
```

---

## 七、常见错误码

| 错误码 | 含义 | 解决方案 |
|---|---|---|
| `RKNN_ERR_MODEL_INVALID` | 模型文件损坏 | 重新下载模型 |
| `RKNN_ERR_MALLOC_FAIL` | 内存分配失败 | 增加 CMA 内存 |
| `RKNN_ERR_TIMEOUT` | NPU 推理超时 | 检查模型复杂度 |
| `EINVAL` | 参数无效 | 检查 ioctl 参数 |
| `ENOMEM` | 内存不足 | 释放内存或重启 |
| `EBUSY` | 设备忙 | 等待或重启设备 |

---

## 八、获取帮助

### 8.1 查看日志

```bash
# 边缘侧
ssh rock@192.168.1.70
journalctl -u neuro-pipeline -f

# 中心侧
tail -f mac-central/logs/central.log
```

---

### 8.2 收集诊断信息

```bash
# 边缘侧
bash tools/collect_diagnostics.sh > diagnostics.txt

# 包含:
# - 系统信息 (uname -a)
# - NPU 版本 (cat /sys/kernel/debug/rknpu/version)
# - 内存信息 (free -h)
# - V4L2 设备 (v4l2-ctl --list-devices)
# - 库依赖 (ldd neuro_pipeline_edge)
```

---

### 8.3 提交 Issue

如果问题无法解决，请提交 Issue 并附上:
1. 错误日志（完整堆栈）
2. 系统信息（OS、内核版本、NPU 版本）
3. 复现步骤
4. 诊断信息（diagnostics.txt）

---

## 九、Week 3/4 新增问题

### 9.1 gRPC 连接失败

**症状**: `grpc._channel._InactiveRpcError: StatusCode.UNAVAILABLE`

**排查**:
1. 确认 central server 已启动: `python -m src.main --config config.yaml`
2. 检查端口占用: `lsof -i :50051`
3. 检查防火墙: `sudo pfctl -sr | grep 50051`
4. 验证网络连通: `nc -zv <central_ip> 50051`

**常见原因**:
- Central server 未启动或崩溃
- 端口被其他进程占用
- Edge 设备 `grpc_server` 配置 IP 错误

### 9.2 MLX 模型加载失败

**症状**: `FileNotFoundError: Model not found` 或 `ImportError: mlx_lm`

**排查**:
1. 确认模型目录存在: `ls mac-central/models/Llama-3.2-3B-Instruct-4bit-mlx/`
2. 确认 mlx_lm 已安装: `pip show mlx-lm`
3. 确认 config.yaml 中 `central.model_path` 指向正确目录

**模型转换**:
```bash
bash tools/convert_mlx_model.sh
```

### 9.3 4-bit 量化精度问题

**症状**: MLX 推理结果质量下降或出现乱码

**排查**:
1. 验证模型完整性: `ls -la models/Llama-3.2-3B-Instruct-4bit-mlx/`（应有 config.json, model.safetensors, tokenizer.json 等）
2. 测试推理: `python3 -c "from mlx_lm import load, generate; m, t = load('models/Llama-3.2-3B-Instruct-4bit-mlx'); print(generate(m, t, prompt='Hello', max_tokens=20))"`
3. 如果质量不可接受，可重新转换为 8-bit: 修改 `tools/convert_mlx_model.sh` 中 `--q-bits 4` 为 `--q-bits 8`

### 9.4 VLM 规则不触发

**症状**: 检测到目标但未触发 VLM 分析

**排查**:
1. 检查 `config.yaml` 中 `vlm_rules` 配置
2. 确认检测置信度超过规则阈值（`min_confidence`）
3. 确认 `class_name` 与 YOLO 输出类名一致
4. 确认 `frame_data` 非空（需要图像数据才能触发 VLM）

### 9.5 Dashboard 无法访问

**症状**: 浏览器无法打开 http://localhost:8080

**排查**:
1. 确认 dashboard 已启动: `cd extensions/dashboard && uvicorn app:app --port 8080`
2. 安装依赖: `pip install -r extensions/dashboard/requirements.txt`
3. 检查端口: `lsof -i :8080`

---

## 十、参考资料

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — 部署指南
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构设计
- [KPI Report](performance/kpi-report.md) — 性能基准报告
- [Week 2 Retrospective](devlog/week2-retro.md) — Week 2 复盘
- [RKNN API 文档](https://github.com/airockchip/rknn-toolkit2/tree/master/doc)
- [MPP 文档](https://github.com/rockchip-linux/mpp/wiki)

---

**文档版本**: v1.1.0
**最后更新**: 2026-02-14
