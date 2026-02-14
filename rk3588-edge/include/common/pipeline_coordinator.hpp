#ifndef APP_PIPELINE_COORDINATOR_HPP_
#define APP_PIPELINE_COORDINATOR_HPP_

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <thread>

namespace communication {
class GRPCClient;
}

namespace app {

/**
 * @brief Orchestrates the edge data pipeline:
 *        V4L2/MPP → RGA → RKNN → YOLO PostProcess.
 *
 * Supports two input modes:
 *   - Camera: live V4L2 capture
 *   - Video file: MPP hardware decode
 */
class PipelineCoordinator {
 public:
  struct Config {
    std::string video_source;       // Video file path, or empty for camera
    std::string model_path;         // .rknn model file
    std::string camera_device = "/dev/video0";  // V4L2 device
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

}  // namespace app

#endif  // APP_PIPELINE_COORDINATOR_HPP_
