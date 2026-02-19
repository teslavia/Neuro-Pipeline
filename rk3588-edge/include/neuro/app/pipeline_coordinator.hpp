#ifndef NEURO_APP_PIPELINE_COORDINATOR_HPP_
#define NEURO_APP_PIPELINE_COORDINATOR_HPP_

#include <atomic>
#include <memory>
#include <thread>

#include "neuro/app/pipeline_config.hpp"

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
  // Backward-compatible aliases — existing code using
  // PipelineCoordinator::Config / CameraConfig keeps compiling.
  using Config = PipelineConfig;

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
