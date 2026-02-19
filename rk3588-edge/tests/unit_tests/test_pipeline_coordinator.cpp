#include <gtest/gtest.h>
#include "neuro/app/pipeline_coordinator.hpp"

using namespace neuro::app;

// --- Config defaults ---

TEST(PipelineCoordinatorConfig, DefaultValues) {
  PipelineCoordinator::Config cfg;
  EXPECT_EQ(cfg.width, 1920u);
  EXPECT_EQ(cfg.height, 1080u);
  EXPECT_EQ(cfg.model_width, 640u);
  EXPECT_EQ(cfg.model_height, 640u);
  EXPECT_EQ(cfg.fps, 30u);
  EXPECT_EQ(cfg.npu_core_mask, 0);
  EXPECT_FLOAT_EQ(cfg.confidence_threshold, 0.5f);
  EXPECT_FLOAT_EQ(cfg.nms_threshold, 0.45f);
  EXPECT_EQ(cfg.max_frames, 0u);
  EXPECT_FALSE(cfg.grpc.enabled);
  EXPECT_EQ(cfg.device_id, "edge-001");
  EXPECT_TRUE(cfg.cameras.empty());
}

TEST(PipelineCoordinatorConfig, CameraConfig) {
  CameraConfig cam;
  EXPECT_EQ(cam.device, "/dev/video0");
  EXPECT_EQ(cam.width, 1920u);
  EXPECT_EQ(cam.height, 1080u);
  EXPECT_EQ(cam.fps, 30u);
  EXPECT_TRUE(cam.label.empty());
}

TEST(PipelineCoordinatorConfig, MultiCameraSetup) {
  PipelineCoordinator::Config cfg;
  for (int i = 0; i < 3; ++i) {
    CameraConfig cam;
    cam.device = "/dev/video" + std::to_string(i);
    cam.label = "cam" + std::to_string(i);
    cfg.cameras.push_back(cam);
  }
  EXPECT_EQ(cfg.cameras.size(), 3u);
  EXPECT_EQ(cfg.cameras[1].device, "/dev/video1");
  EXPECT_EQ(cfg.cameras[2].label, "cam2");
}

TEST(PipelineCoordinatorConfig, DedupDefaults) {
  PipelineCoordinator::Config cfg;
  EXPECT_FLOAT_EQ(cfg.dedup_iou_threshold, 0.5f);
  EXPECT_DOUBLE_EQ(cfg.dedup_ttl_seconds, 2.0);
}

TEST(PipelineCoordinatorConfig, FrameSkipDefault) {
  PipelineCoordinator::Config cfg;
  EXPECT_EQ(cfg.frame_skip_interval, 0u);
}

// --- Lifecycle tests (require mock HAL) ---

#ifdef USE_MOCK_HAL
TEST(PipelineCoordinatorLifecycle, InitializeSucceeds) {
  PipelineCoordinator::Config cfg;
  cfg.model_path = "/tmp/test_model.rknn";
  cfg.video_source = "";  // camera mode
  PipelineCoordinator coord(cfg);
  EXPECT_TRUE(coord.Initialize());
}

TEST(PipelineCoordinatorLifecycle, StatsAfterInit) {
  PipelineCoordinator::Config cfg;
  cfg.model_path = "/tmp/test_model.rknn";
  PipelineCoordinator coord(cfg);
  coord.Initialize();
  EXPECT_EQ(coord.GetFrameCount(), 0u);
  EXPECT_EQ(coord.GetFPS(), 0u);
  EXPECT_DOUBLE_EQ(coord.GetAvgLatencyMs(), 0.0);
  EXPECT_FALSE(coord.IsRunning());
}

TEST(PipelineCoordinatorLifecycle, StartStop) {
  PipelineCoordinator::Config cfg;
  cfg.model_path = "/tmp/test_model.rknn";
  cfg.max_frames = 5;  // Stop after 5 frames
  PipelineCoordinator coord(cfg);
  ASSERT_TRUE(coord.Initialize());
  coord.Start();
  // Wait for pipeline to finish (max_frames=5 should be fast with mock)
  for (int i = 0; i < 100 && coord.IsRunning(); ++i) {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  coord.Stop();
  EXPECT_FALSE(coord.IsRunning());
  EXPECT_GE(coord.GetFrameCount(), 5u);
}

TEST(PipelineCoordinatorLifecycle, ApplyCommandNoOp) {
  PipelineCoordinator::Config cfg;
  cfg.model_path = "/tmp/test_model.rknn";
  PipelineCoordinator coord(cfg);
  coord.Initialize();
  // Should not crash
  coord.ApplyCommand(0, "test");
}
#endif
