#ifndef NEURO_APP_PIPELINE_CONFIG_HPP_
#define NEURO_APP_PIPELINE_CONFIG_HPP_

#include <cstdint>
#include <string>
#include <vector>

namespace neuro::app {

/// gRPC communication settings.
struct GRPCConfig {
  bool enabled = false;
  std::string server_address = "192.168.1.100:50051";
  bool compression = true;
  size_t cache_queue_max_entries = 1000;
  size_t cache_queue_max_memory_bytes = 64 * 1024 * 1024;
};

/// Event-triggered video recording settings.
struct RecordingConfig {
  bool enabled = false;
  double pre_seconds = 10.0;
  double post_seconds = 30.0;
  std::string output_dir = "/opt/neuro-pipeline/recordings";
  uint32_t fps = 30;
};

/// Single model definition for multi-model mode.
struct ModelConfig {
  std::string model_id;
  std::string model_path;
  std::string postprocessor = "yolov5";  // "yolov5" or "yolov8"
  int npu_core = -1;                     // -1 = auto
};

/// Model cascade: light model screens, heavy model refines uncertain detections.
struct CascadeConfig {
  bool enabled = false;
  std::string light_model_id;
  std::string heavy_model_id;
  float min_confidence = 0.3f;
  float max_confidence = 0.7f;
  int max_cascade_per_frame = 5;
  float roi_padding = 0.1f;
};

/// Per-camera configuration for multi-camera mode.
struct CameraConfig {
  std::string device = "/dev/video0";
  uint32_t width = 1920;
  uint32_t height = 1080;
  uint32_t fps = 30;
  std::string label;
};

/// Top-level pipeline configuration (composed from sub-configs).
struct PipelineConfig {
  // Input source
  std::string video_source;
  std::string camera_device = "/dev/video0";
  std::string device_id = "edge-001";
  uint32_t width = 1920;
  uint32_t height = 1080;
  uint32_t fps = 30;

  // Model / inference
  std::string model_path;
  uint32_t model_width = 640;
  uint32_t model_height = 640;
  int npu_core_mask = 0;
  float confidence_threshold = 0.5f;
  float nms_threshold = 0.45f;

  // Runtime limits
  uint32_t max_frames = 0;
  uint32_t frame_skip_interval = 0;

  // Dedup
  float dedup_iou_threshold = 0.5f;
  double dedup_ttl_seconds = 2.0;

  // RTSP (internal flag)
  bool use_rtsp = false;

  // Sub-configs
  GRPCConfig grpc;
  RecordingConfig recording;
  CascadeConfig cascade;
  std::vector<CameraConfig> cameras;
  std::vector<ModelConfig> models;

  // v2 feature toggles
  bool enable_temporal_tracker = false;
  bool enable_adaptive_fps = false;
  bool enable_multi_model = false;

  // v2.3: Frame data for VLM
  bool send_frame_data = false;
  int jpeg_quality = 70;
};

}  // namespace neuro::app

#endif  // NEURO_APP_PIPELINE_CONFIG_HPP_
