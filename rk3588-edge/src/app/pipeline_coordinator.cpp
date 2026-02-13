#include "common/pipeline_coordinator.hpp"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <thread>
#include <vector>

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
  explicit Impl(const Config& config) : config_(config) {
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
      std::cerr << "[Pipeline] DRM allocator init failed" << std::endl;
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
        std::cerr << "[Pipeline] V4L2 camera init failed" << std::endl;
        return false;
      }
    } else {
      rk_hal::MPPDecoder::Config dec_cfg;
      dec_cfg.width = config_.width;
      dec_cfg.height = config_.height;
      dec_cfg.codec = 7;  // H.264
      decoder_ = std::make_unique<rk_hal::MPPDecoder>(dec_cfg);
      if (!decoder_->Initialize()) {
        std::cerr << "[Pipeline] MPP decoder init failed" << std::endl;
        return false;
      }
      // Load video file
      video_file_.open(config_.video_source, std::ios::binary);
      if (!video_file_.is_open()) {
        std::cerr << "[Pipeline] Failed to open video: "
                  << config_.video_source << std::endl;
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
      std::cerr << "[Pipeline] RGA init failed" << std::endl;
      return false;
    }

    // RKNN engine
    ai_inference::RKNNEngine::Config rknn_cfg;
    rknn_cfg.model_path = config_.model_path;
    rknn_cfg.core_mask = config_.npu_core_mask;
    engine_ = std::make_unique<ai_inference::RKNNEngine>(rknn_cfg);
    if (!engine_->Initialize()) {
      std::cerr << "[Pipeline] RKNN engine init failed" << std::endl;
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
        std::cout << "[Pipeline] gRPC client connected" << std::endl;
      } else {
        std::cerr << "[Pipeline] gRPC connection failed, running in local mode" << std::endl;
      }
    }

    std::cout << "[Pipeline] All components initialized" << std::endl;
    return true;
  }

  void Run(std::atomic<bool>& running, double& avg_latency,
           uint32_t& measured_fps, uint64_t& frame_count) {
    using Clock = std::chrono::steady_clock;

    if (use_camera_ && camera_) {
      if (!camera_->Start()) {
        std::cerr << "[Pipeline] Camera start failed" << std::endl;
        running = false;
        return;
      }
    }

    std::cout << "[Pipeline] Processing loop started" << std::endl;
    auto fps_start = Clock::now();
    uint64_t fps_frames = 0;

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
          std::cout << "[Pipeline] End of video stream" << std::endl;
          break;
        }
        continue;
      }

      // 2. Preprocess: NV12 → RGB888 640×640
      auto processed = rga_->Process(frame);
      if (!processed) {
        std::cerr << "[Pipeline] RGA processing failed" << std::endl;
        if (use_camera_) camera_->ReleaseFrame(frame);
        continue;
      }

      // 3. NPU inference
      if (!engine_->Infer(processed)) {
        std::cerr << "[Pipeline] Inference failed" << std::endl;
        if (use_camera_) camera_->ReleaseFrame(frame);
        continue;
      }

      // 4. Postprocess
      auto detections = postprocessor_->Process(
          engine_->GetOutputs(), config_.width, config_.height);

      // 5. Output results
      if (!detections.empty()) {
        std::printf("[Frame %lu] %zu detections:\n",
                    frame_count, detections.size());
        for (const auto& det : detections) {
          std::printf("  [%s] %.1f%% at (%.3f,%.3f)-(%.3f,%.3f)\n",
                      det.class_name.c_str(), det.confidence * 100.0f,
                      det.x_min, det.y_min, det.x_max, det.y_max);
        }

        // Send to central server if gRPC enabled
        if (grpc_client_ && grpc_client_->IsConnected()) {
          neuro_pipeline::DetectionResult result;
          result.set_frame_id(frame_count);
          result.set_timestamp_us(
              std::chrono::duration_cast<std::chrono::microseconds>(
                  t0.time_since_epoch()).count());

          for (const auto& det : detections) {
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
            std::cerr << "[Pipeline] Failed to send detection to server" << std::endl;
          }
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

      // Check frame limit
      if (config_.max_frames > 0 && frame_count >= config_.max_frames) {
        std::cout << "[Pipeline] Reached frame limit: " << config_.max_frames << std::endl;
        break;
      }
    }

    if (use_camera_ && camera_) {
      camera_->Stop();
    }

    std::cout << "[Pipeline] Stopped. Processed " << frame_count
              << " frames, avg latency=" << avg_latency << "ms" << std::endl;
  }

 private:
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

  // Run pipeline in a dedicated thread
  std::thread([this]() {
    impl_->Run(running_, avg_latency_ms_, measured_fps_, frame_count_);
    running_ = false;
  }).detach();
}

void PipelineCoordinator::Stop() {
  if (running_.exchange(false)) {
    // Give pipeline thread time to finish current frame
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    std::cout << "[Pipeline] Stop requested" << std::endl;
  }
}

}  // namespace app
