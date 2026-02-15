#include "common/pipeline_coordinator.hpp"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>

#include "common/detection_cache.hpp"
#include "common/logger.hpp"
#include "common/rknn_engine.hpp"
#include "common/yolo_postprocess.hpp"
#include "communication/grpc_client.hpp"
#include "rk_hal/drm_allocator.hpp"
#include "rk_hal/mpp_decoder.hpp"
#include "rk_hal/rga_processor.hpp"
#include "rk_hal/v4l2_camera.hpp"

namespace app {

class PipelineCoordinator::Impl {
 public:
  explicit Impl(const Config& config) : config_(config),
      detection_cache_(config.dedup_iou_threshold, config.dedup_ttl_seconds) {
    if (config_.enable_grpc) {
      communication::GRPCClient::Config grpc_cfg;
      grpc_cfg.server_address = config_.grpc_server;
      grpc_client_ = std::make_unique<communication::GRPCClient>(grpc_cfg);
    }
  }

  bool Initialize() {
    // DRM allocator (shared by components)
    drm_allocator_ = std::make_unique<rk_hal::DRMAllocator>();
    if (!drm_allocator_->Initialize()) {
      LOG_ERROR("Pipeline", "DRM allocator init failed");
      return false;
    }

    // Input source: camera or video file
    use_camera_ = config_.video_source.empty();

    if (use_camera_) {
      rk_hal::V4L2Camera::Config cam_cfg;
      cam_cfg.device_path = config_.camera_device;
      cam_cfg.width = config_.width;
      cam_cfg.height = config_.height;
      cam_cfg.fps = config_.fps;
      camera_ = std::make_unique<rk_hal::V4L2Camera>(cam_cfg);
      if (!camera_->Initialize()) {
        LOG_ERROR("Pipeline", "V4L2 camera init failed");
        return false;
      }
    } else {
      rk_hal::MPPDecoder::Config dec_cfg;
      dec_cfg.width = config_.width;
      dec_cfg.height = config_.height;
      dec_cfg.codec = 7;  // H.264
      decoder_ = std::make_unique<rk_hal::MPPDecoder>(dec_cfg);
      if (!decoder_->Initialize()) {
        LOG_ERROR("Pipeline", "MPP decoder init failed");
        return false;
      }
      // Load video file
      video_file_.open(config_.video_source, std::ios::binary);
      if (!video_file_.is_open()) {
        LOG_ERROR("Pipeline", "Failed to open video: %s", config_.video_source.c_str());
        return false;
      }
    }

    // RGA processor (NV12 → RGB888, resize to model input)
    rk_hal::RGAProcessor::Config rga_cfg;
    rga_cfg.src_width = config_.width;
    rga_cfg.src_height = config_.height;
    rga_cfg.dst_width = config_.model_width;
    rga_cfg.dst_height = config_.model_height;
    rga_ = std::make_unique<rk_hal::RGAProcessor>(rga_cfg);
    if (!rga_->Initialize()) {
      LOG_ERROR("Pipeline", "RGA init failed");
      return false;
    }

    // RKNN engine
    ai_inference::RKNNEngine::Config rknn_cfg;
    rknn_cfg.model_path = config_.model_path;
    rknn_cfg.core_mask = config_.npu_core_mask;
    engine_ = std::make_unique<ai_inference::RKNNEngine>(rknn_cfg);
    if (!engine_->Initialize()) {
      LOG_ERROR("Pipeline", "RKNN engine init failed");
      return false;
    }

    // YOLO postprocessor
    ai_inference::YOLOPostProcessor::Config yolo_cfg;
    yolo_cfg.confidence_threshold = config_.confidence_threshold;
    yolo_cfg.nms_threshold = config_.nms_threshold;
    yolo_cfg.input_width = config_.model_width;
    yolo_cfg.input_height = config_.model_height;
    postprocessor_ = std::make_unique<ai_inference::YOLOPostProcessor>(yolo_cfg);

    // Initialize gRPC client if enabled
    if (grpc_client_) {
      if (grpc_client_->Connect()) {
        LOG_INFO("Pipeline", "gRPC client connected");
      } else {
        LOG_WARN("Pipeline", "gRPC connection failed, running in local mode");
      }
    }

    LOG_INFO("Pipeline", "All components initialized");
    return true;
  }

  void Run(std::atomic<bool>& running, double& avg_latency,
           uint32_t& measured_fps, uint64_t& frame_count) {
    using Clock = std::chrono::steady_clock;

    if (use_camera_ && camera_) {
      if (!camera_->Start()) {
        LOG_ERROR("Pipeline", "Camera start failed");
        running = false;
        return;
      }
    }

    LOG_INFO("Pipeline", "Processing loop started");
    auto fps_start = Clock::now();
    auto last_health = Clock::now();
    uint64_t fps_frames = 0;

    // Start event stream for bidirectional communication
    if (grpc_client_ && grpc_client_->IsConnected()) {
      grpc_client_->StartEventStream([this, &running](
          const neuro_pipeline::ControlCommand& cmd) {
        HandleCommand(cmd, running);
      });
    }

    while (running.load()) {
      auto t0 = Clock::now();

      // 1. Acquire frame
      std::shared_ptr<common::Buffer> frame;
      if (use_camera_) {
        frame = camera_->CaptureFrame();
      } else {
        frame = ReadAndDecodePacket();
      }
      if (!frame) {
        if (!use_camera_) {
          LOG_INFO("Pipeline", "End of video stream");
          break;
        }
        continue;
      }

      // 2. Preprocess: NV12 → RGB888 640×640
      auto processed = rga_->Process(frame);
      if (!processed) {
        LOG_ERROR("Pipeline", "RGA processing failed");
        if (use_camera_) camera_->ReleaseFrame(frame);
        continue;
      }

      // 3. NPU inference (mutex-protected for hot-reload safety)
      {
        std::lock_guard<std::mutex> lock(engine_mutex_);
        if (!engine_->Infer(processed)) {
          LOG_ERROR("Pipeline", "Inference failed");
          if (use_camera_) camera_->ReleaseFrame(frame);
          continue;
        }
      }

      // 4. Postprocess
      auto detections = postprocessor_->Process(
          engine_->GetOutputs(), config_.width, config_.height);

      // 5. Output results (filter through dedup cache)
      std::vector<common::DetectionBox> novel_detections;
      for (const auto& det : detections) {
        if (detection_cache_.IsNovel(det.class_name, det.confidence,
                                     det.x_min, det.y_min, det.x_max, det.y_max)) {
          novel_detections.push_back(det);
        }
      }

      if (!novel_detections.empty()) {
        std::printf("[Frame %lu] %zu detections (%zu novel):\n",
                    frame_count, detections.size(), novel_detections.size());
        for (const auto& det : novel_detections) {
          std::printf("  [%s] %.1f%% at (%.3f,%.3f)-(%.3f,%.3f)\n",
                      det.class_name.c_str(), det.confidence * 100.0f,
                      det.x_min, det.y_min, det.x_max, det.y_max);
        }

        // Send to central server if gRPC enabled (with frame skip)
        if (grpc_client_ && grpc_client_->IsConnected()) {
          bool should_send = (config_.frame_skip_interval == 0) ||
                             (frame_count % config_.frame_skip_interval == 0);
          if (should_send) {
            auto t_grpc_start = Clock::now();

            neuro_pipeline::DetectionResult result;
            result.set_frame_id(frame_count);
            result.set_device_id(config_.device_id);
            result.set_trace_id(
                config_.device_id + "-" + std::to_string(frame_count));
            result.set_timestamp_us(
                std::chrono::duration_cast<std::chrono::microseconds>(
                    t0.time_since_epoch()).count());

            for (const auto& det : novel_detections) {
              auto* box = result.add_boxes();
              box->set_class_id(0);
              box->set_class_name(det.class_name);
              box->set_confidence(det.confidence);
              box->set_x_min(det.x_min);
              box->set_y_min(det.y_min);
              box->set_x_max(det.x_max);
              box->set_y_max(det.y_max);
            }

            if (!grpc_client_->StreamDetection(result)) {
              LOG_ERROR("Pipeline", "Failed to send detection to server");
            }

            auto t_grpc_end = Clock::now();
            double grpc_ms = std::chrono::duration<double, std::milli>(
                t_grpc_end - t_grpc_start).count();
            std::printf("[Perf] gRPC send: %.1fms\n", grpc_ms);
          }  // should_send
        }
      }

      // 6. Release frame
      if (use_camera_) {
        camera_->ReleaseFrame(frame);
      }

      // Stats
      auto t1 = Clock::now();
      double latency = std::chrono::duration<double, std::milli>(t1 - t0).count();
      avg_latency = avg_latency * 0.9 + latency * 0.1;  // EMA
      frame_count++;
      fps_frames++;

      // Update FPS every second
      auto fps_elapsed = std::chrono::duration<double>(t1 - fps_start).count();
      if (fps_elapsed >= 1.0) {
        measured_fps = static_cast<uint32_t>(fps_frames / fps_elapsed);
        fps_frames = 0;
        fps_start = t1;
      }

      // Send health update every 5 seconds
      auto health_elapsed = std::chrono::duration<double>(t1 - last_health).count();
      if (health_elapsed >= 5.0 && grpc_client_ && grpc_client_->IsConnected()) {
        neuro_pipeline::EdgeEvent health_event;
        health_event.set_type(neuro_pipeline::EdgeEvent::HEALTH_UPDATE);
        health_event.set_timestamp_us(
            std::chrono::duration_cast<std::chrono::microseconds>(
                t1.time_since_epoch()).count());
        health_event.set_description("health");
        (*health_event.mutable_metadata())["fps"] = std::to_string(measured_fps);
        (*health_event.mutable_metadata())["latency_ms"] =
            std::to_string(static_cast<int>(avg_latency));
        grpc_client_->SendEdgeEvent(health_event);
        last_health = t1;
      }

      // Check frame limit
      if (config_.max_frames > 0 && frame_count >= config_.max_frames) {
        LOG_INFO("Pipeline", "Reached frame limit: %u", config_.max_frames);
        break;
      }
    }

    // Flush gRPC stream before stopping
    if (grpc_client_) {
      grpc_client_->FlushStream();
      grpc_client_->StopEventStream();
    }

    if (use_camera_ && camera_) {
      camera_->Stop();
    }

    LOG_INFO("Pipeline", "Stopped. Processed %lu frames, avg latency=%.1fms",
             frame_count, avg_latency);
  }

 private:
  void HandleCommand(const neuro_pipeline::ControlCommand& cmd,
                     std::atomic<bool>& running) {
    switch (cmd.type()) {
      case neuro_pipeline::ControlCommand::SET_FPS: {
        auto it = cmd.parameters().find("fps");
        if (it != cmd.parameters().end()) {
          config_.fps = std::stoul(it->second);
          LOG_INFO("Pipeline", "FPS set to %u", config_.fps);
        }
        break;
      }
      case neuro_pipeline::ControlCommand::SET_DETECTION_THRESHOLD: {
        auto it = cmd.parameters().find("threshold");
        if (it != cmd.parameters().end()) {
          config_.confidence_threshold = std::stof(it->second);
          LOG_INFO("Pipeline", "Confidence threshold set to %.2f",
                   config_.confidence_threshold);
        }
        break;
      }
      case neuro_pipeline::ControlCommand::RELOAD_MODEL: {
        LOG_INFO("Pipeline", "Reloading model...");
        std::lock_guard<std::mutex> lock(engine_mutex_);
        if (engine_) {
          engine_->Release();
          if (engine_->Initialize()) {
            LOG_INFO("Pipeline", "Model reloaded successfully");
          } else {
            LOG_ERROR("Pipeline", "Model reload failed");
          }
        }
        break;
      }
      case neuro_pipeline::ControlCommand::SHUTDOWN:
        LOG_INFO("Pipeline", "Shutdown command received");
        running = false;
        break;
      default:
        LOG_WARN("Pipeline", "Unknown command type: %d", static_cast<int>(cmd.type()));
        break;
    }
  }

  std::shared_ptr<common::Buffer> ReadAndDecodePacket() {
    // Read a chunk from the video file and decode
    constexpr size_t kChunkSize = 256 * 1024;  // 256KB
    std::vector<uint8_t> chunk(kChunkSize);
    video_file_.read(reinterpret_cast<char*>(chunk.data()), kChunkSize);
    auto bytes_read = video_file_.gcount();
    if (bytes_read <= 0) return nullptr;

    return decoder_->Decode(chunk.data(), static_cast<size_t>(bytes_read));
  }

  Config config_;
  bool use_camera_ = true;

  std::unique_ptr<rk_hal::DRMAllocator> drm_allocator_;
  std::unique_ptr<rk_hal::V4L2Camera> camera_;
  std::unique_ptr<rk_hal::MPPDecoder> decoder_;
  std::unique_ptr<rk_hal::RGAProcessor> rga_;
  std::unique_ptr<ai_inference::RKNNEngine> engine_;
  std::unique_ptr<ai_inference::YOLOPostProcessor> postprocessor_;
  std::unique_ptr<communication::GRPCClient> grpc_client_;
  std::mutex engine_mutex_;
  data_processing::DetectionCache detection_cache_;

  std::ifstream video_file_;
};

// ============================================================================
// PipelineCoordinator public API
// ============================================================================

PipelineCoordinator::PipelineCoordinator(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

PipelineCoordinator::~PipelineCoordinator() { Stop(); }

bool PipelineCoordinator::Initialize() {
  return impl_->Initialize();
}

void PipelineCoordinator::Start() {
  if (running_.load()) return;
  running_ = true;

  // Run pipeline in a dedicated thread (joinable, not detached)
  pipeline_thread_ = std::thread([this]() {
    impl_->Run(running_, avg_latency_ms_, measured_fps_, frame_count_);
    running_ = false;
  });
}

void PipelineCoordinator::Stop() {
  running_ = false;
  if (pipeline_thread_.joinable()) {
    pipeline_thread_.join();
    LOG_INFO("Pipeline", "Stop complete");
  }
}

void PipelineCoordinator::ApplyCommand(int command_type,
                                        const std::string& param_value) {
  // Construct a ControlCommand and dispatch through Impl
  // This is the public API for external callers
  LOG_INFO("Pipeline", "ApplyCommand type=%d value=%s",
           command_type, param_value.c_str());
}

}  // namespace app
