# Neuro-Pipeline API Reference

**Version**: 1.0.0
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
| `SET_DETECTION_THRESHOLD` | `{"threshold": "0.6"}` | 调整检测置信度阈值 |
| `ENABLE_DEBUG` | `{"enabled": "true"}` | 开关调试日志 |
| `SHUTDOWN` | `{}` | 优雅关机 |

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

## Message Definitions

### DetectionResult

```protobuf
message DetectionResult {
  uint64 frame_id = 1;             // 唯一帧标识
  uint64 timestamp_us = 2;         // 微秒时间戳 (单调时钟)
  repeated BoundingBox boxes = 3;  // 检测到的目标
  bytes frame_data = 4;            // 可选 JPEG 编码帧 (仅事件触发时发送)
  DeviceMetrics metrics = 5;       // 设备性能指标
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

---

## Error Handling

| gRPC Status | Meaning | Client Action |
|---|---|---|
| `OK` | 成功 | 继续 |
| `UNAVAILABLE` | 网络错误 | 指数退避重试 |
| `INVALID_ARGUMENT` | 请求格式错误 | 修复客户端代码 |
| `RESOURCE_EXHAUSTED` | 服务器过载 | 降低发送频率 |
| `DEADLINE_EXCEEDED` | 超时 | 检查网络延迟 |

## Performance Recommendations

- **批量检测**: 最大 30 results/sec，含视频帧时最大 1 FPS
- **压缩**: `frame_data` 使用 JPEG quality 85
- **Keepalive**: 30s interval, 10s timeout
- **Max Message Size**: 4 MB

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

_Generated from `proto/neuro_pipeline.proto` and HAL headers. Last updated: 2026-02-13_
