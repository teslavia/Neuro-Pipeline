#ifndef NEURO_APP_PIPELINE_COORDINATOR_HPP_
#define NEURO_APP_PIPELINE_COORDINATOR_HPP_

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace neuro::comm {
class GRPCClient;
}

namespace neuro::app {

/**
 * @brief Orchestrates the edge data pipeline:
 *        V4L2/MPP → RGA → RKNN → YOLO PostProcess.
 *
 * Supports two input modes:
 *   - Camera: live V4L2 capture (single or multi-camera)
 *   - Video file: MPP hardware decode
 */
class PipelineCoordinator {
 public:
  struct CameraConfig {
    std::string device = "/dev/video0";
    uint32_t width = 1920;
    uint32_t height = 1080;
    uint32_t fps = 30;
    std::string label;  // Optional human-readable label
  };

  struct Config {
    std::string video_source;       // Video file path, RTSP URL, or empty for camera
    std::string model_path;         // .rknn model file
    std::string camera_device = "/dev/video0";  // V4L2 device (single-cam compat)
    std::string device_id = "edge-001";  // Unique device identifier
    uint32_t width = 1920;
    uint32_t height = 1080;
    uint32_t model_width = 640;
    uint32_t model_height = 640;
    uint32_t fps = 30;
    int npu_core_mask = 0;          // 0=auto
    float confidence_threshold = 0.5f;
    float nms_threshold = 0.45f;
    uint32_t max_frames = 0;        // 0=unlimited
    bool enable_grpc = false;       // Enable gRPC communication
    std::string grpc_server = "192.168.1.100:50051";
    bool grpc_compression = true;
    // Offline cache queue config
    size_t cache_queue_max_entries = 1000;
    size_t cache_queue_max_memory_bytes = 64 * 1024 * 1024;
    uint32_t frame_skip_interval = 0;  // 0=send every frame, N=send every Nth
    std::vector<CameraConfig> cameras;  // Multi-camera configs (empty = single-cam)
    float dedup_iou_threshold = 0.5f;
    double dedup_ttl_seconds = 2.0;
    bool use_rtsp = false;          // Internal: set when video_source starts with rtsp://

    struct RecordingConfig {
      bool enabled = false;
      double pre_seconds = 10.0;
      double post_seconds = 30.0;
      std::string output_dir = "/opt/neuro-pipeline/recordings";
      uint32_t fps = 30;
    };
    RecordingConfig recording;

    // v2 feature toggles
    bool enable_temporal_tracker = false;
    bool enable_adaptive_fps = false;
    bool enable_multi_model = false;

    // v2: Multi-model config
    struct ModelConfig {
      std::string model_id;
      std::string model_path;
      std::string postprocessor = "yolov5";  // "yolov5" or "yolov8"
      int npu_core = -1;                     // -1 = auto
    };
    std::vector<ModelConfig> models;

    // v2.1: Model cascade config (light model -> heavy model for uncertain detections)
    struct CascadeConfig {
      bool enabled = false;
      std::string light_model_id;    // Fast screening model (e.g., "yolov5s")
      std::string heavy_model_id;    // Precise analysis model (e.g., "yolov8s")
      float min_confidence = 0.3f;   // Min confidence to consider cascade
      float max_confidence = 0.7f;   // Below this, trigger heavy model
      int max_cascade_per_frame = 5; // Max ROIs to process per frame
      float roi_padding = 0.1f;      // Padding around detection for ROI
    };
    CascadeConfig cascade;

    // v2.3: Frame data (JPEG) sending for VLM analysis on central
    bool send_frame_data = false;   // Send JPEG-encoded frame with detections
    int jpeg_quality = 70;          // JPEG quality 1-100
  };

  explicit PipelineCoordinator(const Config& config);
  ~PipelineCoordinator();

  PipelineCoordinator(const PipelineCoordinator&) = delete;
  PipelineCoordinator& operator=(const PipelineCoordinator&) = delete;

  bool Initialize();
  void Start();
  void Stop();
  bool IsRunning() const { return running_.load(); }

  /// Apply a control command from central server.
  void ApplyCommand(int command_type, const std::string& param_value);

  /// Get performance stats.
  double GetAvgLatencyMs() const { return avg_latency_ms_; }
  uint32_t GetFPS() const { return measured_fps_; }
  uint64_t GetFrameCount() const { return frame_count_; }

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  Config config_;
  std::atomic<bool> running_{false};
  std::thread pipeline_thread_;
  double avg_latency_ms_ = 0;
  uint32_t measured_fps_ = 0;
  uint64_t frame_count_ = 0;
};

}  // namespace neuro::app

#endif  // NEURO_APP_PIPELINE_COORDINATOR_HPP_
