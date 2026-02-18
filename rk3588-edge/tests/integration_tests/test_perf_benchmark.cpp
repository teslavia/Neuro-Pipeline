#include <gtest/gtest.h>
#include <chrono>
#include <thread>
#include "neuro/app/pipeline_coordinator.hpp"

using namespace neuro::app;

#ifndef USE_MOCK_HAL
TEST(PerfBenchmark, DISABLED_E2ELatency) {
  // This test requires real hardware and model file
  // Run manually on device: ./neuro_pipeline_tests --gtest_also_run_disabled_tests --gtest_filter=PerfBenchmark.DISABLED_E2ELatency

  PipelineCoordinator::Config cfg;
  cfg.model_path = "models/yolov5s-640-640.rknn";
  cfg.camera_device = "/dev/video0";
  cfg.max_frames = 30;

  PipelineCoordinator pipeline(cfg);

  try {
    if (!pipeline.Initialize()) {
      GTEST_SKIP() << "Hardware unavailable (camera/NPU/model not found)";
    }
  } catch (const std::exception& e) {
    GTEST_SKIP() << "Initialization failed: " << e.what();
  }

  auto start = std::chrono::steady_clock::now();
  pipeline.Start();

  // Wait for pipeline to process frames
  while (pipeline.IsRunning()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  auto elapsed = std::chrono::duration<double>(
    std::chrono::steady_clock::now() - start).count();

  uint32_t frame_count = pipeline.GetFrameCount();
  uint32_t fps = pipeline.GetFPS();
  double avg_latency = pipeline.GetAvgLatencyMs();

  // Assertions
  EXPECT_GT(frame_count, 0u) << "No frames processed";
  EXPECT_GT(fps, 0u) << "FPS is zero";
  EXPECT_LT(avg_latency, 100.0) << "Latency exceeds 100ms threshold";
  EXPECT_GT(elapsed, 0.0) << "Invalid elapsed time";

  // Performance report
  std::cout << "\n=== Performance Benchmark Results ===\n";
  std::cout << "Frames Processed: " << frame_count << "\n";
  std::cout << "FPS: " << fps << "\n";
  std::cout << "Avg Latency: " << avg_latency << " ms\n";
  std::cout << "Total Time: " << elapsed << " s\n";
  std::cout << "====================================\n";
}
#endif
