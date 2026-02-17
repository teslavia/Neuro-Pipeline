#include "common/pipeline_coordinator.hpp"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>

#include "common/adaptive_fps.hpp"
#include "common/constants.hpp"
#include "common/detection_cache.hpp"
#include "common/edge_metrics.hpp"
#include "common/logger.hpp"
#include "common/memory_pool.hpp"
#include "common/npu_scheduler.hpp"
#include "common/rknn_engine.hpp"
#include "common/temporal_tracker.hpp"
#include "common/video_recorder.hpp"
#include "common/yolo_postprocess.hpp"
#include "common/yolov8_postprocess.hpp"
#include "common/multi_model_manager.hpp"
#include "communication/grpc_client.hpp"
#include "rk_hal/drm_allocator.hpp"
#include "rk_hal/mpp_decoder.hpp"
#include "rk_hal/rga_processor.hpp"
#include "rk_hal/rtsp_source.hpp"
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

    // Input source: RTSP, camera(s), or video file
    use_rtsp_ = (!config_.video_source.empty() &&
                 config_.video_source.substr(0, 7) == "rtsp://");
    use_camera_ = config_.video_source.empty();

    if (use_rtsp_) {
      // RTSP mode
      rk_hal::RTSPSource::Config rtsp_cfg;
      rtsp_cfg.url = config_.video_source;
      rtsp_cfg.width = config_.width;
      rtsp_cfg.height = config_.height;
      rtsp_cfg.fps = config_.fps;
      rtsp_source_ = std::make_unique<rk_hal::RTSPSource>(rtsp_cfg);
      if (!rtsp_source_->Initialize()) {
        LOG_ERROR("Pipeline", "RTSP source init failed: %s", config_.video_source.c_str());
        return false;
      }
      LOG_INFO("Pipeline", "RTSP source: %s", config_.video_source.c_str());
    } else if (use_camera_) {
      if (!config_.cameras.empty()) {
        // Multi-camera mode
        for (size_t i = 0; i < config_.cameras.size(); ++i) {
          const auto& cam_cfg_in = config_.cameras[i];
          rk_hal::V4L2Camera::Config cam_cfg;
          cam_cfg.device_path = cam_cfg_in.device;
          cam_cfg.width = cam_cfg_in.width;
          cam_cfg.height = cam_cfg_in.height;
          cam_cfg.fps = cam_cfg_in.fps;
          auto cam = std::make_unique<rk_hal::V4L2Camera>(cam_cfg);
          if (!cam->Initialize()) {
            LOG_ERROR("Pipeline", "Camera[%zu] init failed: %s", i, cam_cfg_in.device.c_str());
            return false;
          }
          cameras_.push_back(std::move(cam));

          // Per-camera RGA processor
          rk_hal::RGAProcessor::Config rga_cfg;
          rga_cfg.src_width = cam_cfg_in.width;
          rga_cfg.src_height = cam_cfg_in.height;
          rga_cfg.dst_width = config_.model_width;
          rga_cfg.dst_height = config_.model_height;
          auto rga = std::make_unique<rk_hal::RGAProcessor>(rga_cfg);
          if (!rga->Initialize()) {
            LOG_ERROR("Pipeline", "RGA[%zu] init failed", i);
            return false;
          }
          rga_processors_.push_back(std::move(rga));
        }
        LOG_INFO("Pipeline", "Multi-camera: %zu cameras initialized", cameras_.size());
      } else {
        // Single-camera fallback
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

    // RGA processor (shared for single-camera / video mode)
    if (cameras_.empty()) {
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

    // Memory pool for inference buffers (model_w * model_h * 3 bytes)
    size_t buf_size = config_.model_width * config_.model_height * 3;
    inference_pool_ = std::make_unique<data_processing::MemoryPool>(
        buf_size, common::kDefaultBufferCount);
    LOG_INFO("Pipeline", "Memory pool: %zu x %zu bytes", common::kDefaultBufferCount, buf_size);

    // NPU scheduler (multi-camera mode with all cores enabled)
    if (!config_.cameras.empty() && config_.npu_core_mask == 7) {
      npu_scheduler_ = std::make_unique<ai_inference::NPUScheduler>(
          ai_inference::NPUScheduler::Strategy::kRoundRobin);
      LOG_INFO("Pipeline", "NPU scheduler: round-robin across 3 cores");
    }

    // Video recorder (event-triggered)
    if (config_.recording.enabled) {
      common::VideoRecorder::Config rec_cfg;
      rec_cfg.enabled = true;
      rec_cfg.pre_seconds = config_.recording.pre_seconds;
      rec_cfg.post_seconds = config_.recording.post_seconds;
      rec_cfg.output_dir = config_.recording.output_dir;
      rec_cfg.fps = config_.recording.fps > 0 ? config_.recording.fps : config_.fps;
      video_recorder_ = std::make_unique<common::VideoRecorder>(rec_cfg);
      LOG_INFO("Pipeline", "Video recorder: pre=%.0fs post=%.0fs dir=%s",
               rec_cfg.pre_seconds, rec_cfg.post_seconds, rec_cfg.output_dir.c_str());
    }

    // Initialize gRPC client if enabled
    if (grpc_client_) {
      if (grpc_client_->Connect()) {
        LOG_INFO("Pipeline", "gRPC client connected");
      } else {
        LOG_WARN("Pipeline", "gRPC connection failed, running in local mode");
      }
    }

    // v2: Temporal tracker (object tracking + behavior detection)
    if (config_.enable_temporal_tracker) {
      data_processing::TemporalTracker::Config tt_cfg;
      temporal_tracker_ = std::make_unique<data_processing::TemporalTracker>(tt_cfg);
      LOG_INFO("Pipeline", "Temporal tracker enabled");
    }

    // v2: Adaptive FPS controller
    if (config_.enable_adaptive_fps) {
      app::AdaptiveFPSController::Config afps_cfg;
      afps_cfg.min_fps = 5;
      afps_cfg.max_fps = config_.fps;
      adaptive_fps_ = std::make_unique<app::AdaptiveFPSController>(afps_cfg);
      LOG_INFO("Pipeline", "Adaptive FPS enabled (range: %u-%u)",
               afps_cfg.min_fps, afps_cfg.max_fps);
    }

    // v2: Multi-model manager — load models from config
    if (config_.enable_multi_model && !config_.models.empty()) {
      model_mgr_ = std::make_unique<ai_inference::MultiModelManager>(
          config_.models.size());
      for (const auto& m : config_.models) {
        if (!model_mgr_->LoadModel(m.model_id, m.model_path, m.npu_core)) {
          LOG_ERROR("Pipeline", "Failed to load model: %s", m.model_id.c_str());
          continue;
        }
        auto* slot = model_mgr_->GetModel(m.model_id);
        if (slot) {
          if (m.postprocessor == "yolov8") {
            ai_inference::YOLOv8PostProcessor::Config v8_cfg;
            v8_cfg.confidence_threshold = config_.confidence_threshold;
            v8_cfg.nms_threshold = config_.nms_threshold;
            v8_cfg.input_width = config_.model_width;
            v8_cfg.input_height = config_.model_height;
            slot->postprocessor =
                std::make_unique<ai_inference::YOLOv8PostProcessor>(v8_cfg);
          } else {
            ai_inference::YOLOPostProcessor::Config v5_cfg;
            v5_cfg.confidence_threshold = config_.confidence_threshold;
            v5_cfg.nms_threshold = config_.nms_threshold;
            v5_cfg.input_width = config_.model_width;
            v5_cfg.input_height = config_.model_height;
            slot->postprocessor =
                std::make_unique<ai_inference::YOLOPostProcessor>(v5_cfg);
          }
          LOG_INFO("Pipeline", "Multi-model: %s (%s) on core %d",
                   m.model_id.c_str(), m.postprocessor.c_str(), m.npu_core);
        }
      }
      LOG_INFO("Pipeline", "Multi-model manager: %zu models loaded",
               model_mgr_->ModelCount());
    }

    LOG_INFO("Pipeline", "All components initialized");
    return true;
  }

  void Run(std::atomic<bool>& running, double& avg_latency,
           uint32_t& measured_fps, uint64_t& frame_count) {
    using Clock = std::chrono::steady_clock;

    // RAII guard for memory pool allocations
    struct PoolGuard {
      data_processing::MemoryPool* pool;
      void* ptr;
      PoolGuard(data_processing::MemoryPool* p) : pool(p), ptr(p ? p->Allocate() : nullptr) {}
      ~PoolGuard() { if (pool && ptr) pool->Free(ptr); }
      void* get() const { return ptr; }
    };

    if (use_rtsp_) {
      if (rtsp_source_ && !rtsp_source_->Start()) {
        LOG_ERROR("Pipeline", "RTSP source start failed");
        running = false;
        return;
      }
    } else if (use_camera_) {
      if (!cameras_.empty()) {
        for (auto& cam : cameras_) {
          if (!cam->Start()) {
            LOG_ERROR("Pipeline", "Multi-camera start failed");
            running = false;
            return;
          }
        }
      } else if (camera_) {
        if (!camera_->Start()) {
          LOG_ERROR("Pipeline", "Camera start failed");
          running = false;
          return;
        }
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
      std::shared_ptr<common::Buffer> processed;
      size_t active_cam_idx = 0;

      // Allocate inference buffer from pool (RAII)
      PoolGuard pool_buf(inference_pool_.get());

      if (use_rtsp_) {
        frame = rtsp_source_->CaptureFrame();
        if (!frame) {
          LOG_INFO("Pipeline", "RTSP stream ended");
          break;
        }
        processed = rga_->Process(frame);
      } else if (use_camera_ && !cameras_.empty()) {
        // Multi-camera: round-robin across cameras
        active_cam_idx = frame_count % cameras_.size();
        frame = cameras_[active_cam_idx]->CaptureFrame();
        if (!frame) continue;
        // 2. Preprocess with per-camera RGA
        processed = rga_processors_[active_cam_idx]->Process(frame);
      } else if (use_camera_) {
        frame = camera_->CaptureFrame();
        if (!frame) continue;
        // 2. Preprocess
        processed = rga_->Process(frame);
      } else {
        frame = ReadAndDecodePacket();
        if (!frame) {
          LOG_INFO("Pipeline", "End of video stream");
          break;
        }
        // 2. Preprocess
        processed = rga_->Process(frame);
      }
      if (!processed) {
        LOG_ERROR("Pipeline", "RGA processing failed");
        if (use_rtsp_) {
          rtsp_source_->ReleaseFrame(frame);
        } else if (use_camera_ && !cameras_.empty()) {
          cameras_[active_cam_idx]->ReleaseFrame(frame);
        } else if (use_camera_) {
          camera_->ReleaseFrame(frame);
        }
        continue;
      }

      // 3. NPU inference (mutex-protected for hot-reload safety)
      std::vector<common::DetectionBox> detections;
      {
        std::lock_guard<std::mutex> lock(engine_mutex_);

        // Multi-model path: use active model from MultiModelManager
        if (model_mgr_) {
          auto* active = model_mgr_->GetActiveModel();
          if (active && active->engine) {
            auto t_infer_start = Clock::now();
            if (!active->engine->Infer(processed)) {
              LOG_ERROR("Pipeline", "Inference failed (model: %s)",
                        active->model_id.c_str());
              common::EdgeMetrics::Instance().IncrementInferenceErrors();
              if (use_rtsp_) {
                rtsp_source_->ReleaseFrame(frame);
              } else if (use_camera_ && !cameras_.empty()) {
                cameras_[active_cam_idx]->ReleaseFrame(frame);
              } else if (use_camera_) {
                camera_->ReleaseFrame(frame);
              }
              continue;
            }
            double infer_ms = std::chrono::duration<double, std::milli>(
                Clock::now() - t_infer_start).count();
            common::EdgeMetrics::Instance().RecordInferenceLatencyMs(infer_ms);

            if (active->postprocessor) {
              detections = active->postprocessor->Process(
                  active->engine->GetOutputs(), config_.width, config_.height);
            }
          }
        } else {
          // Single-model path (original)
          // Multi-camera NPU core scheduling via NPUScheduler
          if (npu_scheduler_) {
            int core = npu_scheduler_->SelectCore();
            engine_->SetCoreMask(core);
          } else if (!cameras_.empty() && config_.npu_core_mask == 7) {
            int core = 1 << (active_cam_idx % 3);
            engine_->SetCoreMask(core);
          }
          auto t_infer_start = Clock::now();
          if (!engine_->Infer(processed)) {
            LOG_ERROR("Pipeline", "Inference failed");
            common::EdgeMetrics::Instance().IncrementInferenceErrors();
            if (use_rtsp_) {
              rtsp_source_->ReleaseFrame(frame);
            } else if (use_camera_ && !cameras_.empty()) {
              cameras_[active_cam_idx]->ReleaseFrame(frame);
            } else if (use_camera_) {
              camera_->ReleaseFrame(frame);
            }
            continue;
          }
          double infer_ms = std::chrono::duration<double, std::milli>(
              Clock::now() - t_infer_start).count();
          common::EdgeMetrics::Instance().RecordInferenceLatencyMs(infer_ms);

          detections = postprocessor_->Process(
              engine_->GetOutputs(), config_.width, config_.height);
        }
      }

      // v2: Temporal tracking — assign track IDs and detect behaviors
      std::vector<uint64_t> track_ids;
      if (temporal_tracker_) {
        track_ids = temporal_tracker_->Update(detections, frame_count);

        auto behaviors = temporal_tracker_->DetectBehaviors();
        for (const auto& [tid, btype] : behaviors) {
          if (btype != data_processing::BehaviorType::kNone && grpc_client_ && grpc_client_->IsConnected()) {
            neuro_pipeline::EdgeEvent behavior_event;
            behavior_event.set_type(neuro_pipeline::EdgeEvent::DETECTION_ALERT);
            behavior_event.set_timestamp_us(
                std::chrono::duration_cast<std::chrono::microseconds>(
                    Clock::now().time_since_epoch()).count());
            behavior_event.set_description("behavior_detected");
            (*behavior_event.mutable_metadata())["track_id"] = std::to_string(tid);
            (*behavior_event.mutable_metadata())["behavior_type"] = std::to_string(static_cast<int>(btype));
            grpc_client_->SendEdgeEvent(behavior_event);
          }
        }
      }

      // Push every frame to video recorder ring buffer (pre-event buffer)
      if (video_recorder_ && frame) {
        video_recorder_->PushFrame(frame);
      }

      // 5. Output results (filter through dedup cache)
      std::vector<common::DetectionBox> novel_detections;
      for (const auto& det : detections) {
        if (detection_cache_.IsNovel(det.class_name, det.confidence,
                                     det.x_min, det.y_min, det.x_max, det.y_max)) {
          novel_detections.push_back(det);
        }
      }

      if (!novel_detections.empty()) {
        common::EdgeMetrics::Instance().IncrementDetectionsTotal(novel_detections.size());

        // Video recorder: trigger recording on novel detections
        if (video_recorder_) {
          video_recorder_->TriggerRecording(novel_detections[0].class_name);
        }

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

            for (size_t di = 0; di < novel_detections.size(); ++di) {
              const auto& det = novel_detections[di];
              auto* box = result.add_boxes();
              box->set_class_id(0);
              box->set_class_name(det.class_name);
              box->set_confidence(det.confidence);
              box->set_x_min(det.x_min);
              box->set_y_min(det.y_min);
              box->set_x_max(det.x_max);
              box->set_y_max(det.y_max);
              // v2: set track_id if temporal tracker assigned one
              if (!track_ids.empty() && di < track_ids.size()) {
                box->set_track_id(track_ids[di]);
              }
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
      if (use_rtsp_) {
        rtsp_source_->ReleaseFrame(frame);
      } else if (use_camera_ && !cameras_.empty()) {
        cameras_[active_cam_idx]->ReleaseFrame(frame);
      } else if (use_camera_) {
        camera_->ReleaseFrame(frame);
      }

      // Stats
      auto t1 = Clock::now();
      double latency = std::chrono::duration<double, std::milli>(t1 - t0).count();
      avg_latency = avg_latency * 0.9 + latency * 0.1;  // EMA
      frame_count++;
      fps_frames++;
      common::EdgeMetrics::Instance().IncrementFramesProcessed();

      // Update FPS every second
      auto fps_elapsed = std::chrono::duration<double>(t1 - fps_start).count();
      if (fps_elapsed >= common::kFPSUpdateIntervalSec) {
        measured_fps = static_cast<uint32_t>(fps_frames / fps_elapsed);
        common::EdgeMetrics::Instance().SetFPS(static_cast<double>(measured_fps));
        fps_frames = 0;
        fps_start = t1;
      }

      auto health_elapsed = std::chrono::duration<double>(t1 - last_health).count();
      if (health_elapsed >= common::kHealthUpdateIntervalSec && grpc_client_ && grpc_client_->IsConnected()) {
        neuro_pipeline::EdgeEvent health_event;
        health_event.set_type(neuro_pipeline::EdgeEvent::HEALTH_UPDATE);
        health_event.set_timestamp_us(
            std::chrono::duration_cast<std::chrono::microseconds>(
                t1.time_since_epoch()).count());
        health_event.set_description("health");
        // Include all edge metrics in health update
        auto& metrics = common::EdgeMetrics::Instance();
        for (const auto& kv : metrics.Snapshot()) {
          (*health_event.mutable_metadata())[kv.first] = kv.second;
        }
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

      // v2: Adaptive FPS — adjust frame delay based on detection activity
      if (adaptive_fps_) {
        adaptive_fps_->Update(static_cast<int>(novel_detections.size()));
        auto delay_us = adaptive_fps_->GetFrameDelayUs();
        if (delay_us > 0) {
          std::this_thread::sleep_for(std::chrono::microseconds(delay_us));
        }
      }
    }

    // Flush gRPC stream before stopping
    if (grpc_client_) {
      grpc_client_->FlushStream();
      grpc_client_->StopEventStream();
    }

    if (use_rtsp_) {
      if (rtsp_source_) rtsp_source_->Stop();
    } else if (use_camera_) {
      if (!cameras_.empty()) {
        for (auto& cam : cameras_) cam->Stop();
      } else if (camera_) {
        camera_->Stop();
      }
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
      case neuro_pipeline::ControlCommand::SWITCH_MODEL_VARIANT: {
        auto it = cmd.parameters().find("model_id");
        if (it != cmd.parameters().end()) {
          if (model_mgr_) {
            std::lock_guard<std::mutex> lock(engine_mutex_);
            if (model_mgr_->SwitchActiveModel(it->second)) {
              LOG_INFO("Pipeline", "Switched to model: %s", it->second.c_str());
            } else {
              LOG_ERROR("Pipeline", "Failed to switch to model: %s",
                        it->second.c_str());
            }
          } else {
            LOG_WARN("Pipeline", "SWITCH_MODEL_VARIANT: multi-model not enabled");
          }
        }
        break;
      }
      case neuro_pipeline::ControlCommand::SET_DETECTION_REGION: {
        auto x = cmd.parameters().find("x_min");
        auto y = cmd.parameters().find("y_min");
        auto x2 = cmd.parameters().find("x_max");
        auto y2 = cmd.parameters().find("y_max");
        if (x != cmd.parameters().end() && y != cmd.parameters().end() &&
            x2 != cmd.parameters().end() && y2 != cmd.parameters().end()) {
          LOG_INFO("Pipeline", "Detection region set: (%.3f,%.3f)-(%.3f,%.3f)",
                   std::stof(x->second), std::stof(y->second),
                   std::stof(x2->second), std::stof(y2->second));
        }
        break;
      }
      case neuro_pipeline::ControlCommand::SET_SENSITIVITY: {
        auto it = cmd.parameters().find("sensitivity");
        if (it != cmd.parameters().end()) {
          float sens = std::stof(it->second);
          config_.confidence_threshold = 1.0f - sens;
          LOG_INFO("Pipeline", "Sensitivity set to %.2f (threshold=%.2f)",
                   sens, config_.confidence_threshold);
        }
        break;
      }
      default:
        LOG_WARN("Pipeline", "Unknown command type: %d", static_cast<int>(cmd.type()));
        break;
    }
  }

  std::shared_ptr<common::Buffer> ReadAndDecodePacket() {
    // Read a chunk from the video file and decode
    constexpr size_t kChunkSize = common::kVideoChunkSize;
    std::vector<uint8_t> chunk(kChunkSize);
    video_file_.read(reinterpret_cast<char*>(chunk.data()), kChunkSize);
    auto bytes_read = video_file_.gcount();
    if (bytes_read <= 0) return nullptr;

    return decoder_->Decode(chunk.data(), static_cast<size_t>(bytes_read));
  }

  Config config_;
  bool use_camera_ = true;
  bool use_rtsp_ = false;

  std::unique_ptr<rk_hal::DRMAllocator> drm_allocator_;
  std::unique_ptr<rk_hal::V4L2Camera> camera_;           // Single-camera fallback
  std::vector<std::unique_ptr<rk_hal::V4L2Camera>> cameras_;  // Multi-camera
  std::unique_ptr<rk_hal::MPPDecoder> decoder_;
  std::unique_ptr<rk_hal::RTSPSource> rtsp_source_;       // RTSP input
  std::unique_ptr<rk_hal::RGAProcessor> rga_;             // Single-camera/video RGA
  std::vector<std::unique_ptr<rk_hal::RGAProcessor>> rga_processors_;  // Per-camera RGA
  std::unique_ptr<ai_inference::RKNNEngine> engine_;
  std::unique_ptr<ai_inference::YOLOPostProcessor> postprocessor_;
  std::unique_ptr<communication::GRPCClient> grpc_client_;
  std::mutex engine_mutex_;
  data_processing::DetectionCache detection_cache_;
  std::unique_ptr<data_processing::MemoryPool> inference_pool_;
  std::unique_ptr<ai_inference::NPUScheduler> npu_scheduler_;
  std::unique_ptr<common::VideoRecorder> video_recorder_;
  std::unique_ptr<data_processing::TemporalTracker> temporal_tracker_;
  std::unique_ptr<app::AdaptiveFPSController> adaptive_fps_;
  std::unique_ptr<ai_inference::MultiModelManager> model_mgr_;

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
