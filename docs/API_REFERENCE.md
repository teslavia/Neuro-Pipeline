# Neuro-Pipeline API Reference

**Version**: 2.3.0
**Protocol**: gRPC with Protocol Buffers 3
**Generated From**: `proto/neuro_pipeline.proto`

---

## Service: NeuroPipelineService

边缘-云通信的核心 gRPC 服务。

### RPC Methods

#### 1. StreamDetectionResults

**Type**: Client Streaming (Edge → Central)

```protobuf
rpc StreamDetectionResults(stream DetectionResult) returns (StreamResponse);
```

**Description**: 边缘设备将 YOLO 检测结果流式传输到中心服务器。

**C++ Client Example**:
```cpp
grpc::ClientContext context;
StreamResponse response;
auto stream = stub_->StreamDetectionResults(&context, &response);

for (const auto& detection : detections) {
  DetectionResult result;
  result.set_frame_id(detection.frame_id);
  result.set_timestamp_us(GetTimestampUs());
  // ... populate bounding boxes
  stream->Write(result);
}
stream->WritesDone();
grpc::Status status = stream->Finish();
```

**Python Server Example**:
```python
async def StreamDetectionResults(self, request_iterator, context):
    frames_received = 0
    async for result in request_iterator:
        await self.orchestrator.process_detection(result)
        frames_received += 1
    return StreamResponse(success=True, frames_received=frames_received)
```

---

#### 2. SendControlCommand

**Type**: Unary RPC (Central → Edge)

```protobuf
rpc SendControlCommand(ControlCommand) returns (CommandResponse);
```

**Description**: 中心服务器向边缘设备发送控制指令。

**Supported Commands**:

| CommandType | Parameters | Description |
|---|---|---|
| `SET_FPS` | `{"fps": "15"}` | 调整摄像头帧率 |
| `CHANGE_MODEL` | `{"model_path": "/models/yolov8n.rknn"}` | 切换 AI 模型 |
| `RELOAD_MODEL` | `{}` | 热重载当前模型（无需重启） |
| `SET_DETECTION_THRESHOLD` | `{"threshold": "0.6"}` | 调整检测置信度阈值 |
| `ENABLE_DEBUG` | `{"enabled": "true"}` | 开关调试日志 |
| `SHUTDOWN` | `{}` | 优雅关机 |
| `SWITCH_MODEL_VARIANT` | `{"model_id": "yolov8s"}` | (v2) 切换到指定模型变体 |
| `SET_DETECTION_REGION` | `{"roi": "x,y,w,h"}` | (v2) 更新检测 ROI (VLM 引导) |
| `SET_SENSITIVITY` | `{"level": "high"}` | (v2) 调整检测灵敏度 (VLM 引导) |

---

#### 3. BidirectionalEventStream

**Type**: Bidirectional Streaming

```protobuf
rpc BidirectionalEventStream(stream EdgeEvent) returns (stream CentralEvent);
```

**Description**: 双向事件流，边缘发送事件，中心返回响应。

**Edge Event Types**:
- `DETECTION_ALERT` — 关键检测告警（如限制区域内检测到人员）
- `SYSTEM_ERROR` — 系统级错误
- `MODEL_LOADED` — 模型加载完成
- `HEALTH_UPDATE` — 周期性健康心跳

**Central Event Types**:
- `COMMAND_ACK` — 指令确认
- `INFERENCE_RESULT` — VLM 推理结果
- `ALERT` — 中心分析告警

---

#### 4. HealthCheck

**Type**: Unary RPC

```protobuf
rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
```

**Description**: 健康检查接口。

---

#### 5. RegisterDevice

**Type**: Unary RPC

```protobuf
rpc RegisterDevice(DeviceRegistration) returns (RegistrationResponse);
```

**Description**: 边缘设备注册到中心服务器，获取 device_id。

**DeviceRegistration**:
```protobuf
message DeviceRegistration {
  string device_name = 1;
  string device_type = 2;  // e.g., "RK3588"
  map<string, string> metadata = 3;
}
```

**RegistrationResponse**:
```protobuf
message RegistrationResponse {
  string device_id = 1;
  bool success = 2;
  string message = 3;
}
```

---

#### 6. ManageModel (v2)

**Type**: Unary RPC

```protobuf
rpc ManageModel(ModelManagementRequest) returns (ModelManagementResponse);
```

**Description**: 模型生命周期管理 — 部署、卸载、查询、回滚模型。

**Actions**:

| Action | Parameters | Description |
|---|---|---|
| `DEPLOY` | `model_id`, `model_path`, `npu_core` | 部署模型到指定 NPU 核心 |
| `UNDEPLOY` | `model_id` | 从设备卸载模型 |
| `LIST` | — | 列出已部署的模型 |
| `ROLLBACK` | `model_id` | 回滚到上一版本 |
| `STATUS` | `model_id` | 获取模型部署状态 |

**ModelManagementRequest**:
```protobuf
message ModelManagementRequest {
  enum Action { DEPLOY = 0; UNDEPLOY = 1; LIST = 2; ROLLBACK = 3; STATUS = 4; }
  Action action = 1;
  ModelInfo model = 2;
  string target_device_id = 3;
  int32 npu_core = 4;  // 0-2, -1 = auto
}
```

---

#### 7. QueryTimeSeries (v2)

**Type**: Unary RPC

```protobuf
rpc QueryTimeSeries(TimeSeriesQuery) returns (TimeSeriesResponse);
```

**Description**: 查询时序指标数据。

**TimeSeriesQuery**:
```protobuf
message TimeSeriesQuery {
  string metric_name = 1;      // "detections_count", "fps", "latency"
  string device_id = 2;
  double start_time = 3;       // Unix timestamp
  double end_time = 4;         // Unix timestamp (0 = now)
  string aggregation = 5;      // "avg", "sum", "max", "min", "count"
  int32 bucket_seconds = 6;    // Aggregation bucket size
}
```

---

## Message Definitions

### DetectionResult

```protobuf
message DetectionResult {
  uint64 frame_id = 1;             // 唯一帧标识
  uint64 timestamp_us = 2;         // 微秒时间戳 (单调时钟)
  repeated BoundingBox boxes = 3;  // 检测到的目标
  bytes frame_data = 4;            // 可选 JPEG 编码帧 (仅事件触发时发送)
  DeviceMetrics metrics = 5;       // 设备性能指标
  string trace_id = 6;             // 分布式追踪 trace ID (v1.1.0+)
  string device_id = 7;            // 设备标识 (v1.1.0+)
  string span_id = 8;              // 分布式追踪 span ID (v1.1.0+)

  // v2 extensions
  string model_id = 100;                  // 产生检测的模型 ID
  repeated float feature_vector = 101;    // 帧级嵌入向量 (ReID/相似度)
}
```

### BoundingBox

```protobuf
message BoundingBox {
  uint32 class_id = 1;     // COCO 数据集类别 ID
  string class_name = 2;   // 可读类别名
  float confidence = 3;    // 检测置信度 [0.0, 1.0]
  float x_min = 4;         // 归一化坐标 [0.0, 1.0]
  float y_min = 5;
  float x_max = 6;
  float y_max = 7;

  // v2 extensions
  uint64 track_id = 100;   // 对象跟踪 ID (TemporalTracker 分配)
}
```

**Coordinate System**: 归一化 [0.0, 1.0]，相对于帧宽高。

### DeviceMetrics

```protobuf
message DeviceMetrics {
  float cpu_usage = 1;       // CPU 使用率 [0.0, 100.0]
  float npu_usage = 2;       // NPU 使用率 [0.0, 100.0]
  float memory_used_mb = 3;  // 内存使用 (MB)
  float temperature_c = 4;   // 设备温度 (°C)
  uint32 fps = 5;            // 当前处理帧率
}
```

### VideoFrame

```protobuf
message VideoFrame {
  uint64 frame_id = 1;
  uint64 timestamp_us = 2;
  uint32 width = 3;
  uint32 height = 4;
  PixelFormat format = 5;   // RGB888, NV12, JPEG
  bytes data = 6;
}
```

### BehaviorAlert (v2)

```protobuf
message BehaviorAlert {
  string device_id = 1;
  uint64 timestamp_us = 2;
  string behavior_type = 3;       // "loitering", "running", "lingering", "crowd"
  float severity = 4;             // [0.0, 1.0]
  uint64 track_id = 5;            // 关联的跟踪对象
  string description = 6;
  map<string, string> metadata = 7;
}
```

### TimeSeriesPoint (v2)

```protobuf
message TimeSeriesPoint {
  double timestamp = 1;           // Unix 时间戳 (秒)
  double value = 2;
  map<string, string> labels = 3; // 可选标签
}
```

### TimeSeriesResponse (v2)

```protobuf
message TimeSeriesResponse {
  bool success = 1;
  string message = 2;
  repeated TimeSeriesPoint points = 3;
}
```

### ModelInfo (v2)

```protobuf
message ModelInfo {
  string model_id = 1;            // 唯一模型标识 (e.g., "yolov5s-640")
  string model_path = 2;          // 设备或注册表路径
  string model_type = 3;          // "detection", "classification", "reid"
  string version = 4;             // 语义版本号
  map<string, string> metadata = 5;
}
```

### ModelManagementResponse (v2)

```protobuf
message ModelManagementResponse {
  bool success = 1;
  string message = 2;
  repeated ModelInfo models = 3;  // LIST 操作返回
}
```

---

## Error Handling

| gRPC Status | Meaning | Client Action |
|---|---|---|
| `OK` | 成功 | 继续 |
| `UNAVAILABLE` | 网络错误 | 指数退避重试 |
| `INVALID_ARGUMENT` | 请求格式错误 | 修复客户端代码 |
| `RESOURCE_EXHAUSTED` | 超过速率限制 | 降低发送频率或等待令牌恢复 |
| `DEADLINE_EXCEEDED` | 超时 | 检查网络延迟 |

## Performance Recommendations

- **批量检测**: 最大 30 results/sec，含视频帧时最大 1 FPS
- **压缩**: `frame_data` 使用 JPEG quality 85
- **Keepalive**: 30s interval, 10s timeout
- **Max Message Size**: 16 MB

---

## HAL Layer API (C++)

### DRMAllocator

**文件**: `rk3588-edge/include/rk_hal/drm_allocator.hpp`

```cpp
class DRMAllocator {
public:
  // 分配 DMA-BUF
  int Allocate(uint32_t width, uint32_t height, PixelFormat format);

  // 释放 DMA-BUF
  void Free(int dma_fd);

  // 映射到 CPU 地址空间
  void* Map(int dma_fd, size_t size);

  // 取消映射
  void Unmap(void* addr, size_t size);
};
```

---

### V4L2Camera

**文件**: `rk3588-edge/include/rk_hal/v4l2_camera.hpp`

```cpp
class V4L2Camera {
public:
  // 打开摄像头
  void Open(const std::string& device_path);

  // 设置格式
  void SetFormat(uint32_t width, uint32_t height, PixelFormat format);

  // 启动采集
  void Start();

  // 采集一帧
  Frame CaptureFrame();

  // 停止采集
  void Stop();
};
```

---

### MPPDecoder

**文件**: `rk3588-edge/include/rk_hal/mpp_decoder.hpp`

```cpp
class MPPDecoder {
public:
  // 初始化解码器
  void Init(VideoCodec codec);

  // 解码一帧
  Frame Decode(const uint8_t* data, size_t size);

  // 获取输出 DMA-BUF fd
  int GetOutputFd(const Frame& frame);
};
```

---

### RGAProcessor

**文件**: `rk3588-edge/include/rk_hal/rga_processor.hpp`

```cpp
class RGAProcessor {
public:
  // 缩放 + 格式转换
  Frame Process(const Frame& input, uint32_t dst_width, uint32_t dst_height, PixelFormat dst_format);

  // 裁剪
  Frame Crop(const Frame& input, uint32_t x, uint32_t y, uint32_t width, uint32_t height);
};
```

---

### RKNNEngine

**文件**: `rk3588-edge/include/ai_inference/rknn_engine.hpp`

```cpp
class RKNNEngine {
public:
  // 加载模型
  void LoadModel(const std::string& model_path);

  // 推理
  std::vector<Tensor> Infer(const std::vector<Tensor>& inputs);

  // 获取模型信息
  ModelInfo GetModelInfo() const;
};
```

---

### YOLOPostprocessor

**文件**: `rk3588-edge/include/ai_inference/yolo_postprocess.hpp`

```cpp
class YOLOPostprocessor {
public:
  // 处理 RKNN 输出
  std::vector<Detection> Process(const std::vector<Tensor>& outputs);

  // 设置置信度阈值
  void SetConfidenceThreshold(float threshold);

  // 设置 NMS 阈值
  void SetNMSThreshold(float threshold);
};
```

---

## Central Python API

### AppConfig

**文件**: `mac-central/src/config.py`

```python
@dataclass
class VLMRuleConfig:
    class_name: str = "person"
    min_confidence: float = 0.8
    prompt_template: str = "person_behavior"

@dataclass
class RateLimitingConfig:
    enabled: bool = False
    max_rps: int = 100
    burst: int = 20

@dataclass
class AppConfig:
    central: CentralConfig
    logging: LoggingConfig
    vlm_rules: List[VLMRuleConfig]

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """Load config from YAML file."""
```

### CentralOrchestrator

**文件**: `mac-central/src/pipeline/central_orchestrator.py`

```python
class CentralOrchestrator:
    async def initialize(self) -> None: ...
    async def process_detection(self, result) -> Optional[str]: ...
    async def send_command(self, command) -> None: ...
    async def shutdown(self) -> None: ...
    def get_recent_events(self, limit: int = 50) -> List[Dict]: ...
    def subscribe(self) -> asyncio.Queue: ...
    def unsubscribe(self, q: asyncio.Queue) -> None: ...
```

### MLXInferenceEngine

**文件**: `mac-central/src/inference/mlx_llm_inference.py`

```python
class MLXInferenceEngine:
    async def load_model(self) -> None: ...
    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str: ...
    async def analyze_image(self, image_data: bytes, prompt: str, max_tokens: int = 256) -> str: ...
    async def unload_model(self) -> None: ...
```

---

## Dashboard REST API

**位置**: `extensions/dashboard/app.py`
**技术**: FastAPI + htmx + WebSocket

### V1 Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | 仪表盘页面 (HTML) |
| `/api/status` | GET | 系统状态 JSON |
| `/api/devices` | GET | 已注册设备列表 (v1.1.0+) |
| `/api/events` | GET | 最近事件列表 (`?limit=50&device_id=xxx`) |
| `/api/events` | POST | 推送事件（供 orchestrator 调用） |
| `/api/events/history` | GET | SQLite 历史查询 (`?hours=24&limit=100&device_id=xxx`) |
| `/ws` | WebSocket | 实时事件流 |

### V2 Endpoints (v2.0.0+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/status` | GET | 聚合系统状态（Edge + Central + Analytics） |
| `/api/v2/devices` | GET | 设备列表（含 metrics 和健康状态） |
| `/api/v2/events` | GET | 事件查询（支持过滤和分页） |
| `/api/v2/events/history` | GET | 历史事件（SQLite 查询） |
| `/api/v2/command` | POST | 发送控制命令 |
| `/api/v2/behavior/events` | GET | 行为分析事件 |
| `/api/v2/anomaly/baselines` | GET | 异常检测基线 |
| `/api/v2/anomaly/scores` | GET | 异常分数（支持时间范围过滤） |
| `/api/v2/vlm/guidance` | GET | VLM 配置建议 |
| `/api/v2/vlm/guidance/{id}/apply` | POST | 应用 VLM 建议 |
| `/api/v2/models` | GET | 模型列表和状态 |
| `/api/v2/config` | GET/PUT | 运行时配置 (PUT 触发热重载) |
| `/api/v2/logging/level` | GET/PUT | 动态日志级别 (v2.3) |
| `/api/v2/tracking/objects` | GET | 当前跟踪对象 |

### GET /api/status 响应示例

```json
{
  "edge": {
    "status": "connected",
    "fps": 28.5,
    "npu_usage": 72.0,
    "temperature": 55.0,
    "model": "yolov5s-640-640.rknn"
  },
  "central": {
    "status": "running",
    "model": "Llama-3.2-3B-Instruct-4bit-mlx",
    "uptime_s": 3600,
    "events_processed": 142
  }
}
```

### Authentication (v1.3.0+)

Dashboard routes (except `/healthz`) require HTTP Basic Auth:

```bash
# Set credentials via environment variables
export DASHBOARD_USER=admin
export DASHBOARD_PASS=secret
uvicorn app:app --host 0.0.0.0 --port 8080
```

| Endpoint | Auth Required |
|----------|--------------|
| `/healthz` | No |
| All others | Yes (HTTP Basic) |

---

## Observability Endpoints

### Prometheus Metrics
**Endpoint**: `GET /metrics` (port 9090)
**Format**: Prometheus text exposition

Key metrics:
| Metric | Type | Description |
|--------|------|-------------|
| `neuro_detections_total` | Counter | Total detections processed |
| `neuro_grpc_requests_total` | Counter | gRPC calls by method |
| `neuro_inference_duration_seconds` | Histogram | VLM inference latency |
| `neuro_npu_utilization` | Gauge | Edge NPU usage [0-100] |
| `neuro_vlm_queue_depth` | Gauge | Pending VLM analysis requests |
| `neuro_grpc_validation_errors_total` | Counter | Protobuf validation failures |
| `neuro_control_commands_total` | Counter | Control commands by type |

### Health Probes
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Liveness probe — returns 200 if process is alive |
| `/readyz` | GET | Readiness probe — returns 200 if model loaded and gRPC connected |

### Detection History
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/events/history` | GET | Query SQLite detection history (`?hours=24&limit=100&device_id=xxx`) |

### Device Management (v1.1.0+)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET | List all registered devices with last heartbeat |
| `/api/devices/{device_id}` | GET | Get specific device info |

### Rate Limiting (v1.3.0+)

Token bucket rate limiter per device:

```yaml
rate_limiting:
  enabled: true
  max_rps: 100
  burst: 20
```

When exceeded, `StreamDetectionResults` returns `RESOURCE_EXHAUSTED`.

### Input Validation (v1.3.0+)

All `DetectionResult` messages are validated:
- `device_id` must not be empty
- `confidence` must be in [0.0, 1.0]
- Coordinates (`x_min`, `y_min`, `x_max`, `y_max`) must be in [0.0, 1.0]

Invalid messages are rejected with `INVALID_ARGUMENT` and counted in `grpc_validation_errors_total`.

---

_Generated from `proto/neuro_pipeline.proto` and source code. Last updated: 2026-02-18_
