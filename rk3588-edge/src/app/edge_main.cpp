#include <csignal>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>

#include "common/constants.hpp"
#include "common/pipeline_coordinator.hpp"
#include "app/config_manager.hpp"
#include "common/logger.hpp"

namespace {
volatile std::sig_atomic_t g_shutdown_requested = 0;

void SignalHandler(int signal) {
  std::cout << "\nReceived signal " << signal << ", shutting down..."
            << std::endl;
  g_shutdown_requested = 1;
}
}  // namespace

int main(int argc, char* argv[]) {
  std::cout << "============================================" << std::endl;
  std::cout << "  Neuro-Pipeline Edge " << common::kEdgeVersion << std::endl;
  std::cout << "  RK3588 NPU Inference Engine" << std::endl;
  std::cout << "============================================" << std::endl;

  // Install signal handlers
  std::signal(SIGINT, SignalHandler);
  std::signal(SIGTERM, SignalHandler);

  // Initialize logger (JSON format for structured logging)
  common::Logger::Init("info", "json");

  try {
    // Parse command-line arguments
    app::PipelineCoordinator::Config config;
    config.model_path = "/opt/neuro-pipeline/models/yolov5s-640-640.rknn";
    std::string config_file;

    for (int i = 1; i < argc; ++i) {
      std::string arg = argv[i];
      if ((arg == "-c" || arg == "--config") && i + 1 < argc) {
        config_file = argv[++i];
      } else if ((arg == "-v" || arg == "--video") && i + 1 < argc) {
        config.video_source = argv[++i];
      } else if ((arg == "-m" || arg == "--model") && i + 1 < argc) {
        config.model_path = argv[++i];
      } else if ((arg == "-w" || arg == "--width") && i + 1 < argc) {
        config.width = std::stoul(argv[++i]);
      } else if ((arg == "-h" || arg == "--height") && i + 1 < argc) {
        config.height = std::stoul(argv[++i]);
      } else if ((arg == "-n" || arg == "--max-frames") && i + 1 < argc) {
        config.max_frames = std::stoul(argv[++i]);
      } else if ((arg == "-d" || arg == "--device") && i + 1 < argc) {
        config.camera_device = argv[++i];
      } else if (arg == "--help") {
        std::cout << "Usage: neuro_pipeline_edge [options]\n"
                  << "  -c, --config <path>   Config file (YAML)\n"
                  << "  -v, --video <path>    Input video file (default: camera)\n"
                  << "  -m, --model <path>    RKNN model file\n"
                  << "  -w, --width <N>       Input width (default: 1920)\n"
                  << "  -h, --height <N>      Input height (default: 1080)\n"
                  << "  -n, --max-frames <N>  Stop after N frames (default: unlimited)\n"
                  << "  -d, --device <path>   V4L2 camera device (default: /dev/video0)\n"
                  << std::endl;
        return 0;
      }
    }

    // Load config file if specified (CLI args override config file values)
    if (!config_file.empty()) {
      app::ConfigManager cfg;
      if (cfg.LoadFromFile(config_file)) {
        if (config.video_source.empty())
          config.video_source = cfg.Get("edge.video_source");
        if (config.model_path == "/opt/neuro-pipeline/models/yolov5s-640-640.rknn")
          config.model_path = cfg.Get("edge.model_path", config.model_path);
        config.camera_device = cfg.Get("edge.camera_device", config.camera_device);
        config.width = cfg.GetInt("edge.width", config.width);
        config.height = cfg.GetInt("edge.height", config.height);
        config.fps = cfg.GetInt("edge.fps", config.fps);
        config.npu_core_mask = cfg.GetInt("edge.npu_core_mask", config.npu_core_mask);
        config.confidence_threshold = cfg.GetFloat("edge.confidence_threshold", config.confidence_threshold);
        config.nms_threshold = cfg.GetFloat("edge.nms_threshold", config.nms_threshold);
        config.max_frames = cfg.GetInt("edge.max_frames", config.max_frames);
        config.enable_grpc = cfg.GetBool("edge.enable_grpc", config.enable_grpc);
        config.grpc_server = cfg.Get("edge.grpc_server", config.grpc_server);
        config.device_id = cfg.Get("edge.device_id", config.device_id);
        config.dedup_iou_threshold = cfg.GetFloat("edge.dedup_iou_threshold", config.dedup_iou_threshold);
        config.dedup_ttl_seconds = cfg.GetFloat("edge.dedup_ttl_seconds", static_cast<float>(config.dedup_ttl_seconds));

        // Recording config
        config.recording.enabled = cfg.GetBool("edge.recording.enabled", config.recording.enabled);
        config.recording.pre_seconds = cfg.GetFloat("edge.recording.pre_seconds", static_cast<float>(config.recording.pre_seconds));
        config.recording.post_seconds = cfg.GetFloat("edge.recording.post_seconds", static_cast<float>(config.recording.post_seconds));
        config.recording.output_dir = cfg.Get("edge.recording.output_dir", config.recording.output_dir);
        config.recording.fps = cfg.GetInt("edge.recording.fps", config.recording.fps);

        // v2 feature toggles
        config.enable_temporal_tracker = cfg.GetBool("edge.enable_temporal_tracker", config.enable_temporal_tracker);
        config.enable_adaptive_fps = cfg.GetBool("edge.enable_adaptive_fps", config.enable_adaptive_fps);
        config.enable_multi_model = cfg.GetBool("edge.enable_multi_model", config.enable_multi_model);

        // Multi-camera config: cameras.0.device, cameras.0.width, etc.
        for (int i = 0; i < static_cast<int>(common::kMaxCameras); ++i) {
          std::string prefix = "cameras." + std::to_string(i);
          if (!cfg.Has(prefix + ".device")) break;
          app::PipelineCoordinator::CameraConfig cam;
          cam.device = cfg.Get(prefix + ".device", "/dev/video0");
          cam.width = cfg.GetInt(prefix + ".width", config.width);
          cam.height = cfg.GetInt(prefix + ".height", config.height);
          cam.fps = cfg.GetInt(prefix + ".fps", config.fps);
          cam.label = cfg.Get(prefix + ".label", "cam" + std::to_string(i));
          config.cameras.push_back(cam);
        }
      }
    }

    // Set device_id for structured logging
    common::Logger::SetDeviceId(config.device_id);

    app::PipelineCoordinator coordinator(config);

    if (!coordinator.Initialize()) {
      std::cerr << "[FATAL] Failed to initialize pipeline" << std::endl;
      return 1;
    }

    coordinator.Start();

    // Main loop — wait for shutdown signal
    while (!g_shutdown_requested) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    coordinator.Stop();

  } catch (const std::exception& e) {
    std::cerr << "[FATAL] " << e.what() << std::endl;
    return 1;
  }

  std::cout << "Shutdown complete." << std::endl;
  return 0;
}
