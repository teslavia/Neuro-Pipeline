# 部署验证手册 — Neuro-Pipeline v1.1.0

> 本文档覆盖从零部署到全链路验证的每一步。适用于 Mac Mini (Central) + RK3588 (Edge) 双节点架构。

## 目录

1. [环境准备](#1-环境准备)
2. [Central 节点部署](#2-central-节点部署)
3. [Edge 节点部署](#3-edge-节点部署)
4. [功能验证清单](#4-功能验证清单)
5. [监控栈部署](#5-监控栈部署)
6. [故障排查速查](#6-故障排查速查)

---

## 1. 环境准备

### 1.1 Central (Mac Mini Apple Silicon)

```bash
# Python 环境
python3 --version   # >= 3.10
python3 -m venv venv && source venv/bin/activate
pip install -r mac-central/requirements.txt
pip install fastapi httpx uvicorn jinja2 python-multipart

# 可选依赖（优雅降级，不装也能跑）
pip install opentelemetry-api opentelemetry-sdk   # 分布式追踪
pip install boto3                                  # 云存储上传

# 生成 protobuf 绑定
pip install grpcio-tools
python3 tools/generate_proto.py
```

### 1.2 Edge (RK3588 — Radxa ROCK 5B)

```bash
# 确认设备连通
ssh rock@192.168.1.70 "uname -a && cat /proc/rknpu/version"
# 预期: Linux 6.1.84-8-rk2410 ... / RKNPU driver 0.9.8

# 确认 SDK 库
ssh rock@192.168.1.70 "ls /usr/lib/librknnrt.so /usr/lib/librga.so /usr/lib/librockchip_mpp.so"
```

### 1.3 mTLS 证书（可选，生产环境必须）

```bash
bash tools/certs/generate_certs.sh certs/
# 验证证书链
openssl verify -CAfile certs/ca.pem certs/server.pem
openssl verify -CAfile certs/ca.pem certs/client.pem
# 预期: certs/server.pem: OK / certs/client.pem: OK
```

---

## 2. Central 节点部署

### 2.1 配置文件

编辑 `config.yaml`，关键字段：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `central.host` | 监听地址 | `0.0.0.0` |
| `central.port` | gRPC 端口 | `50051` |
| `central.model_path` | LLM 模型路径 | `models/Llama-3.2-3B-Instruct-4bit-mlx` |
| `tls.enabled` | 启用 mTLS | `false` |
| `storage.db_path` | SQLite 路径 | `data/detections.db` |
| `metrics.enabled` | Prometheus 指标 | `true` |
| `sessions.max_devices` | 最大边缘设备数 | `16` |

### 2.2 启动服务

```bash
cd mac-central
source ../venv/bin/activate

# 开发模式（前台）
python src/main.py --config ../config.yaml

# 生产模式（launchd）
cp ../tools/services/com.neuro-pipeline.central.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.neuro-pipeline.central.plist
launchctl start com.neuro-pipeline.central
```

### 2.3 验证 Central 启动

```bash
# gRPC 端口
lsof -i :50051 | grep LISTEN
# 预期: python ... TCP *:50051 (LISTEN)

# Prometheus 指标
curl -s http://localhost:9090/metrics | head -5
# 预期: # HELP ... / # TYPE ...

# 健康探针
curl -s http://localhost:8080/healthz | python3 -m json.tool
# 预期: {"alive": true}
curl -s http://localhost:8080/readyz | python3 -m json.tool
# 预期: {"ready": true}
```

---

## 3. Edge 节点部署

### 3.1 交叉编译

```bash
# 在 Mac 上构建（Docker）
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh
# 预期: [100%] Built target neuro_edge

# 验证产物
file rk3588-edge/build/neuro_edge
# 预期: ELF 64-bit LSB executable, ARM aarch64
```

### 3.2 部署到设备

```bash
bash tools/deploy_and_run.sh
# 或手动:
rsync -avz rk3588-edge/build/neuro_edge rock@192.168.1.70:/opt/neuro-pipeline/
rsync -avz models/*.rknn rock@192.168.1.70:/opt/neuro-pipeline/models/
scp config.yaml rock@192.168.1.70:/opt/neuro-pipeline/
```

### 3.3 在设备上运行

```bash
ssh rock@192.168.1.70
cd /opt/neuro-pipeline
./neuro_edge --config config.yaml

# 预期输出:
# [INFO][Pipeline] All components initialized
# [INFO][Pipeline] Processing loop started
# [Frame 0] 2 detections (2 novel):
#   [person] 87.3% at (0.123,0.456)-(0.789,0.901)
```

---

## 4. 功能验证清单

逐项验证，每项标注 ✅ 或 ❌。

### 4.1 基础管线

| # | 验证项 | 命令/操作 | 预期结果 |
|---|--------|-----------|----------|
| 1 | gRPC 连接 | Edge 启动后观察 Central 日志 | `New edge stream from edge-001` |
| 2 | 检测推送 | Edge 对准目标 | Central 收到 DetectionResult |
| 3 | SQLite 持久化 | `sqlite3 data/detections.db "SELECT count(*) FROM detections"` | 行数递增 |
| 4 | 重启恢复 | 重启 Central，查询历史 | 历史数据仍在 |

### 4.2 多边缘设备 (v1.1.0)

| # | 验证项 | 命令/操作 | 预期结果 |
|---|--------|-----------|----------|
| 5 | 设备注册 | 启动 2+ Edge | Dashboard `/api/devices` 显示多设备 |
| 6 | 心跳 | 观察 Central 日志 | 每 10s 收到 HEALTH_UPDATE |
| 7 | 会话过期 | 关闭一个 Edge，等 30s | 设备从列表消失 |
| 8 | 按设备过滤 | `curl /api/events?device_id=edge-001` | 只返回该设备事件 |

### 4.3 VLM 推理 (需要模型)

| # | 验证项 | 命令/操作 | 预期结果 |
|---|--------|-----------|----------|
| 9 | VLM 触发 | 检测到 person (conf>0.8) | VLM 分析日志出现 |
| 10 | 多轮对话 | 同设备连续触发 | prompt 包含历史上下文 |
| 11 | 熔断器 | VLM 连续失败 5 次 | 熔断器 OPEN，跳过 VLM |
| 12 | 批量累积 | 短时间多次触发 | 日志显示 batch size > 1 |

### 4.4 mTLS

| # | 验证项 | 命令/操作 | 预期结果 |
|---|--------|-----------|----------|
| 13 | TLS 握手 | `tls.enabled: true`，双端启动 | 连接成功 |
| 14 | 无证书拒绝 | 不带证书的客户端连接 | 连接被拒 |

### 4.5 可观测性

| # | 验证项 | 命令/操作 | 预期结果 |
|---|--------|-----------|----------|
| 15 | Prometheus | `curl localhost:9090/metrics \| grep detections_total` | counter 递增 |
| 16 | 健康探针 | `curl localhost:8080/healthz` | `{"alive": true}` |
| 17 | 就绪探针 | `curl localhost:8080/readyz` | `{"ready": true}` |
| 18 | 告警 | 触发 circuit_breaker_open | CRITICAL 日志 + webhook (如配置) |

---

## 5. 监控栈部署

### 5.1 Prometheus + Grafana

```bash
cd infra
docker compose -f docker-compose.monitoring.yml up -d

# 验证
curl -s http://localhost:9091/-/healthy   # Prometheus
curl -s http://localhost:3000/api/health  # Grafana
# Grafana 默认: admin/admin
```

### 5.2 Grafana Dashboard

1. 打开 `http://localhost:3000`
2. 导航到 Dashboards → Neuro-Pipeline
3. 确认 8 个面板有数据：FPS/设备、检测数、VLM 延迟、gRPC 延迟、连接数、队列深度、熔断器状态、事件总数

---

## 6. 故障排查速查

| 症状 | 排查 | 解决 |
|------|------|------|
| Edge 连不上 Central | `telnet 192.168.1.100 50051` | 检查防火墙、IP、端口 |
| NPU 推理失败 | `cat /proc/rknpu/version` | 确认 driver 0.9.8+，重启 rknn_server |
| SQLite locked | 检查是否多进程写 | 配置已有 retry 机制，检查日志 |
| VLM 超时 | 检查模型路径、内存 | 确认 MLX 模型已下载，内存 >= 8GB |
| Prometheus 无数据 | `curl localhost:9090/metrics` | 确认 `metrics.enabled: true` |
| 设备不显示 | 检查 device_id 配置 | `edge.device_id` 必须唯一 |
| 证书错误 | `openssl verify -CAfile ca.pem server.pem` | 重新生成证书 |

---

## 自动化测试

在部署前/后运行自动化测试套件：

```bash
# 单元测试 (130+)
cd mac-central && pytest tests/ -v -o "addopts=" && cd ..

# Dashboard 测试 (10)
pytest extensions/dashboard/tests/ -v -o "addopts="

# E2E + 混沌测试 (24)
pytest tests/e2e/ tests/chaos/ -v -o "addopts="

# 交叉编译验证
USE_MOCK_HAL=ON bash tools/cross_compile_env/build_rk3588.sh
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh
```

全部通过后方可部署到生产环境。
