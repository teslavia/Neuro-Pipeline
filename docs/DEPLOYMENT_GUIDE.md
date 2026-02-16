# Neuro-Pipeline 部署指南 (Deployment Guide)

**版本**: v1.3.0
**更新日期**: 2026-02-16

---

## 一、概览

本指南涵盖 Neuro-Pipeline 的完整部署流程，包括：
- RK3588 边缘设备交叉编译
- Mac Mini 中心服务器环境配置
- 设备部署与运行
- 常见问题排查
- Web 仪表盘部署

---

## 二、前置条件

### 2.1 开发机器（macOS / Linux）

**必需**:
- Docker 20.10+ (用于交叉编译)
- Git 2.30+
- Python 3.10+ (用于 Protobuf 生成)

**可选**:
- aarch64-linux-gnu-gcc 11+ (本地交叉编译)
- CMake 3.20+

### 2.2 RK3588 边缘设备

**硬件**:
- RK3588 开发板（Radxa ROCK 5B / Orange Pi 5 Plus 等）
- 最低 4GB RAM（推荐 8GB+）
- USB 摄像头或 MIPI CSI 摄像头

**系统**:
- Debian 11+ / Ubuntu 22.04+ (ARM64)
- Kernel 5.10+ (含 RKNPU 驱动)
- SSH 访问权限

**SDK 库**:
- librknnrt.so (RKNN Runtime 2.0+)
- librockchip_mpp.so (MPP 视频解码)
- librga.so (RGA 图像处理)

### 2.3 Mac Mini 中心服务器

**硬件**:
- Apple Silicon (M1/M2/M3/M4)
- 最低 8GB 统一内存（推荐 16GB+）

**系统**:
- macOS 13+ (Ventura / Sonoma / Sequoia)
- Python 3.10+

---

## 三、RK3588 边缘侧部署

### 3.1 准备 Sysroot

从本地 RKSDK 提取交叉编译所需的头文件和库：

```bash
cd /Volumes/TMAC/Satoshi/DEV/mac/TTest/RKPRO/repo
bash tools/cross_compile_env/prepare_sysroot.sh
```

**输出**:
```
✓ Sysroot created: tools/cross_compile_env/sysroot/
  - include/rknn_api.h
  - include/mpp/
  - include/rga/
  - lib/librknnrt.so
  - lib/librockchip_mpp.so.0
  - lib/librga.so.2
```

**验证**:
```bash
ls -lh tools/cross_compile_env/sysroot/lib/*.so*
# 应看到 RKNN/MPP/RGA 库文件
```

---

### 3.2 Docker 交叉编译（推荐）

#### 3.2.1 编译 Mock 版本（本地测试）

```bash
USE_MOCK_HAL=ON bash tools/cross_compile_env/build_rk3588.sh
```

**用途**: 本地开发和单元测试，无需真实硬件。

#### 3.2.2 编译真实版本（设备部署）

```bash
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh
```

**输出**:
```
[Docker] Building neuro-pipeline-builder image...
[Docker] Cross-compiling for RK3588...
[CMake] -- Build type: Release
[CMake] -- USE_MOCK_HAL: OFF
[Make] Building CXX object src/hal/v4l2_camera.cpp.o
...
[Make] Linking CXX executable neuro_pipeline_edge
✓ Build complete: rk3588-edge/build/neuro_pipeline_edge
```

**验证**:
```bash
file rk3588-edge/build/neuro_pipeline_edge
# 输出: ELF 64-bit LSB pie executable, ARM aarch64
```

---

### 3.3 本地交叉编译（无 Docker）

如果已安装 `aarch64-linux-gnu-gcc`:

```bash
cd rk3588-edge
mkdir -p build && cd build

cmake .. \
  -DCMAKE_TOOLCHAIN_FILE=../cmake/aarch64-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DUSE_MOCK_HAL=OFF

make -j$(nproc)
```

---

### 3.4 部署到 RK3588 设备

#### 3.4.1 配置设备连接

编辑 `tools/rk3588_device.conf`:

```bash
DEVICE_HOST="192.168.1.70"
DEVICE_USER="rock"
DEVICE_PORT="22"
DEPLOY_DIR="/opt/neuro-pipeline"
```

#### 3.4.2 部署 SDK 库

首次部署需要上传 RKNN/MPP/RGA 库到设备：

```bash
bash tools/deploy_rk3588.sh
```

**操作**:
1. 创建 `/opt/neuro-pipeline` 目录
2. 上传 `librknnrt.so`, `librockchip_mpp.so`, `librga.so`
3. 配置 `LD_LIBRARY_PATH`

**验证**:
```bash
ssh rock@192.168.1.70
ls -lh /opt/neuro-pipeline/lib/
# 应看到 3 个 .so 文件
```

#### 3.4.3 部署应用程序

```bash
bash tools/deploy_and_run.sh
```

**操作**:
1. 交叉编译（如果需要）
2. 上传 `neuro_pipeline_edge` 到设备
3. 上传模型文件 `models/*.rknn`
4. 远程执行程序

**输出**:
```
[Deploy] Uploading neuro_pipeline_edge...
[Deploy] Uploading models/yolov5s-640-640.rknn...
[Remote] Starting neuro_pipeline_edge...
[INFO] V4L2 camera opened: /dev/video0
[INFO] RKNN model loaded: yolov5s-640-640.rknn
[INFO] Pipeline started, FPS: 28.5
[DETECT] person @ (320, 240) conf=0.87
```

---

### 3.5 模型文件准备

#### 3.5.1 从 RKSDK 复制

```bash
bash tools/download_model.sh
```

自动从 `rknn_model_zoo` 搜索并复制 YOLOv5 模型。

#### 3.5.2 手动下载

```bash
cd rk3588-edge/models
wget https://huggingface.co/airockchip/yolov5/resolve/main/yolov5s_relu.rknn
mv yolov5s_relu.rknn yolov5s-640-640.rknn
```

#### 3.5.3 自行转换（高级）

使用 `rknn-toolkit2` 将 ONNX 转换为 .rknn:

```python
from rknn.api import RKNN

rknn = RKNN()
rknn.config(target_platform='rk3588')
rknn.load_onnx('yolov5s.onnx')
rknn.build(do_quantization=True, dataset='./dataset.txt')
rknn.export_rknn('yolov5s-640-640.rknn')
```

详见 `tools/rknn_toolkit_scripts/convert_yolo.py`

---

## 四、Mac Mini 中心侧部署

### 4.1 环境配置

```bash
cd mac-central

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**核心依赖**:
- `grpcio` — gRPC Python 库
- `grpcio-tools` — Protobuf 编译工具
- `mlx` — Apple Silicon ML 框架
- `mlx-lm` — MLX 大模型推理

---

### 4.2 生成 Protobuf 代码

```bash
cd /Volumes/TMAC/Satoshi/DEV/mac/TTest/RKPRO/repo
python3 tools/generate_proto.py
```

**输出**:
```
✓ Generated: rk3588-edge/src/generated/neuro_pipeline.pb.h
✓ Generated: rk3588-edge/src/generated/neuro_pipeline.pb.cc
✓ Generated: mac-central/src/generated/neuro_pipeline_pb2.py
✓ Generated: mac-central/src/generated/neuro_pipeline_pb2_grpc.py
```

---

### 4.3 下载 MLX 模型

```bash
cd mac-central
bash scripts/download_models.sh
```

**推荐模型**:
- `mlx-community/Qwen2-VL-2B-Instruct` (2GB, VLM)
- `mlx-community/Llama-3.2-3B-Instruct` (3GB, LLM)

**手动下载**:
```bash
huggingface-cli download mlx-community/Qwen2-VL-2B-Instruct \
  --local-dir models/qwen2-vl-2b
```

---

### 4.4 MLX 模型 4-bit 量化（推荐）

将 HuggingFace 格式模型转换为 MLX 原生 4-bit 量化格式，大幅减少内存占用：

```bash
bash tools/convert_mlx_model.sh
```

**效果**:
- 模型大小: 6.4GB → 1.7GB
- 推理速度: ~100 tok/s
- 加载时间: ~755ms

**验证**:
```bash
source .venv/bin/activate
python3 -c "from mlx_lm import load, generate; m, t = load('models/Llama-3.2-3B-Instruct-4bit-mlx'); print(generate(m, t, prompt='Hello', max_tokens=20))"
```

---

### 4.5 启动中心服务器

```bash
cd mac-central
source .venv/bin/activate
python -m src.main --config ../config.yaml
```

**输出**:
```
[INFO] Loading MLX model: models/qwen2-vl-2b
[INFO] gRPC server listening on 0.0.0.0:50051
[INFO] Ready to receive edge events
```

---

## 五、端到端运行

### 5.1 启动中心服务器

**终端 1 (Mac Mini)**:
```bash
cd mac-central
source .venv/bin/activate
python main.py --port 50051
```

### 5.2 启动边缘设备

**终端 2 (SSH 到 RK3588)**:
```bash
ssh rock@192.168.1.70
cd /opt/neuro-pipeline
export LD_LIBRARY_PATH=/opt/neuro-pipeline/lib:$LD_LIBRARY_PATH

./neuro_pipeline_edge \
  --device /dev/video0 \
  --model models/yolov5s-640-640.rknn \
  --server 192.168.1.100:50051
```

**参数说明**:
- `--device`: V4L2 摄像头设备路径
- `--model`: RKNN 模型文件路径
- `--server`: Mac Mini gRPC 服务器地址

---

### 5.3 验证通信

**边缘侧日志**:
```
[INFO] Connected to gRPC server: 192.168.1.100:50051
[DETECT] person @ (320, 240) conf=0.87
[GRPC] Sent detection result, frame_id=12345
```

**中心侧日志**:
```
[GRPC] Received detection: frame_id=12345, boxes=1
[MLX] Running VLM inference...
[MLX] Result: "A person standing in the center of the frame"
[GRPC] Sent response to edge
```

---

## 六、Web 仪表盘

### 6.1 安装依赖

```bash
cd extensions/dashboard
pip install -r requirements.txt
```

### 6.2 启动仪表盘

```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

浏览器访问 http://localhost:8080 查看实时监控面板。

### 6.3 认证配置 (v1.3.0+)

Dashboard 默认启用 HTTP Basic Auth：

```bash
export DASHBOARD_USER=admin
export DASHBOARD_PASS=your_password
uvicorn app:app --host 0.0.0.0 --port 8080
```

`/healthz` 端点免认证，可用于健康检查。

### 6.4 功能

- 设备状态卡片（Edge RK3588 + Central Mac Mini）
- WebSocket 实时事件推送
- REST API: `/api/status`, `/api/events`

---

## 七、性能调优

### 7.1 边缘侧优化

**降低分辨率**:
```bash
./neuro_pipeline_edge --width 640 --height 480
```

**调整 NPU 核心**:
```bash
./neuro_pipeline_edge --npu-cores 3  # 使用全部 3 个 NPU 核心
```

**减少上传频率**:
```bash
./neuro_pipeline_edge --upload-interval 5  # 每 5 帧上传一次
```

---

### 7.2 中心侧优化

**使用量化模型**:
```bash
python main.py --model models/qwen2-vl-2b-4bit
```

**批处理推理**:
```python
# 在 mlx_llm_inference.py 中
results = model.infer_batch(prompts, batch_size=4)
```

---

## 八、系统服务配置（可选）

### 8.1 边缘侧 systemd 服务

创建 `/etc/systemd/system/neuro-pipeline.service`:

```ini
[Unit]
Description=Neuro-Pipeline Edge Service
After=network.target

[Service]
Type=simple
User=rock
WorkingDirectory=/opt/neuro-pipeline
Environment="LD_LIBRARY_PATH=/opt/neuro-pipeline/lib"
ExecStart=/opt/neuro-pipeline/neuro_pipeline_edge \
  --device /dev/video0 \
  --model models/yolov5s-640-640.rknn \
  --server 192.168.1.100:50051
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**启用服务**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable neuro-pipeline
sudo systemctl start neuro-pipeline
sudo systemctl status neuro-pipeline
```

---

### 8.2 中心侧 launchd 服务（macOS）

创建 `~/Library/LaunchAgents/com.neuro-pipeline.central.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.neuro-pipeline.central</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/satoshialan/mac-central/venv/bin/python</string>
        <string>/Users/satoshialan/mac-central/main.py</string>
        <string>--port</string>
        <string>50051</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

**启用服务**:
```bash
launchctl load ~/Library/LaunchAgents/com.neuro-pipeline.central.plist
launchctl start com.neuro-pipeline.central
```

---

## 九、安全配置

### 9.1 mTLS 双向认证（推荐）

**生成证书**:
```bash
cd tools/certs
bash generate_certs.sh
```

**边缘侧配置**:
```bash
./neuro_pipeline_edge \
  --server 192.168.1.100:50051 \
  --tls-cert certs/client.crt \
  --tls-key certs/client.key \
  --tls-ca certs/ca.crt
```

**中心侧配置**:
```python
python main.py \
  --port 50051 \
  --tls-cert certs/server.crt \
  --tls-key certs/server.key \
  --tls-ca certs/ca.crt
```

---

### 9.2 防火墙配置

**RK3588 设备**:
```bash
sudo ufw allow from 192.168.1.0/24 to any port 22
sudo ufw enable
```

**Mac Mini**:
```bash
# 允许 gRPC 端口
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python
```

---

## 十、监控与日志

### 10.1 边缘侧日志

**实时查看**:
```bash
ssh rock@192.168.1.70
tail -f /opt/neuro-pipeline/logs/edge.log
```

**日志级别**:
```bash
./neuro_pipeline_edge --log-level debug
```

---

### 10.2 中心侧日志

**实时查看**:
```bash
tail -f mac-central/logs/central.log
```

**结构化日志**:
```python
import structlog
logger = structlog.get_logger()
logger.info("detection_received", frame_id=12345, boxes=1)
```

---

### 10.3 性能监控

**边缘侧 NPU 利用率**:
```bash
watch -n 1 cat /sys/kernel/debug/rknpu/load
```

**中心侧 GPU 利用率**:
```bash
sudo powermetrics --samplers gpu_power -i 1000
```

---

## 十一、备份与恢复

### 11.1 备份配置

```bash
# 边缘侧
ssh rock@192.168.1.70
tar -czf neuro-pipeline-backup.tar.gz /opt/neuro-pipeline

# 中心侧
tar -czf mac-central-backup.tar.gz mac-central/models mac-central/config
```

---

### 11.2 恢复配置

```bash
# 边缘侧
scp neuro-pipeline-backup.tar.gz rock@192.168.1.70:/tmp/
ssh rock@192.168.1.70
sudo tar -xzf /tmp/neuro-pipeline-backup.tar.gz -C /

# 中心侧
tar -xzf mac-central-backup.tar.gz -C ~/
```

---

## 十二、故障排查

详见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## 十三、可观测性 (Observability)

### 13.1 Prometheus 指标

中心服务器暴露 Prometheus 格式的指标端点：

```bash
curl http://localhost:9090/metrics
```

**核心指标**:
- `neuro_pipeline_detections_total` — 检测事件计数器
- `neuro_pipeline_inference_duration_seconds` — VLM 推理延迟直方图
- `neuro_pipeline_grpc_requests_total` — gRPC 请求计数器
- `neuro_pipeline_circuit_breaker_state` — 熔断器状态 (0=closed, 1=open, 2=half_open)

---

### 13.2 健康探针

**存活探针 (Liveness)**:
```bash
curl http://localhost:9090/healthz
# 返回 200 OK 表示服务运行中
```

**就绪探针 (Readiness)**:
```bash
curl http://localhost:9090/readyz
# 返回 200 OK 表示服务可接受请求（MLX 模型已加载）
```

---

### 13.3 熔断器 (Circuit Breaker)

VLM 推理自动熔断保护：

- **触发条件**: 连续 5 次推理失败
- **熔断时长**: 30 秒
- **恢复策略**: 半开状态尝试 1 次请求，成功则关闭熔断器

**监控熔断状态**:
```bash
curl http://localhost:9090/metrics | grep circuit_breaker_state
```

---

### 13.4 告警 (Alerting)

关键事件触发 webhook POST 通知：

**配置** (config.yaml):
```yaml
alerting:
  enabled: true
  webhook_url: ""
  routes:
    - severity: critical
      webhook_url: "https://critical-alerts.example.com"
    - severity: warning
      webhook_url: "https://warning-alerts.example.com"
  rules:
    - name: "circuit_breaker_open"
      cooldown_seconds: 300
```

**告警事件**:
- VLM 推理失败超过阈值
- 熔断器打开
- 存储写入失败

---

### 13.5 速率限制 (v1.3.0+)

gRPC 令牌桶限流保护中心服务器：

```yaml
rate_limiting:
  enabled: true
  max_rps: 100
  burst: 20
```

超限请求返回 `RESOURCE_EXHAUSTED`，按 device_id 隔离。

---

## 十四、Grafana 监控栈部署 (v1.1.0+)

### 14.1 启动 Prometheus + Grafana

```bash
cd extensions/monitoring
docker-compose up -d
```

**服务**:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

### 14.2 配置数据源

Grafana 自动配置 Prometheus 数据源（通过 provisioning）。

### 14.3 导入仪表盘

仪表盘已自动加载：`extensions/monitoring/grafana/dashboards/neuro-pipeline.json`

**8 个面板**:
1. Detections Total (Counter)
2. VLM Inference Latency (Histogram)
3. NPU Utilization (Gauge)
4. VLM Queue Depth (Gauge)
5. gRPC Requests Total (Counter)
6. Circuit Breaker State (Gauge)
7. Active Devices (Gauge)
8. Error Rate (Counter)

### 14.4 告警规则

编辑 `extensions/monitoring/prometheus/alerts.yml` 添加自定义告警。

---

## 十五、参考资料

- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构设计
- [API_REFERENCE.md](API_REFERENCE.md) — gRPC API 文档
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — 常见问题排查
- [KPI Report](performance/kpi-report.md) — 性能基准报告
- [Week 2 Retrospective](devlog/week2-retro.md) — Week 2 复盘总结

---

**文档版本**: v1.3.0
**最后更新**: 2026-02-16
