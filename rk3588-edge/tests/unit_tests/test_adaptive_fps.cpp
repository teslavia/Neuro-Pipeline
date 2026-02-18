#include <gtest/gtest.h>

#include "neuro/pipeline/adaptive_fps.hpp"

namespace {

TEST(AdaptiveFPSTest, StartsAtIdleFPS) {
  neuro::pipeline::AdaptiveFPSController::Config cfg;
  cfg.idle_fps = 10;
  cfg.active_fps = 30;
  neuro::pipeline::AdaptiveFPSController controller(cfg);

  EXPECT_EQ(controller.GetTargetFPS(), 10u);
}

TEST(AdaptiveFPSTest, RampsUpOnDetection) {
  neuro::pipeline::AdaptiveFPSController::Config cfg;
  cfg.idle_fps = 10;
  cfg.active_fps = 30;
  cfg.ramp_up_frames = 1;
  neuro::pipeline::AdaptiveFPSController controller(cfg);

  EXPECT_EQ(controller.GetTargetFPS(), 10u);

  // One frame with detections should ramp up
  controller.Update(3);
  EXPECT_GE(controller.GetTargetFPS(), 20u);
}

TEST(AdaptiveFPSTest, RampsDownOnIdle) {
  neuro::pipeline::AdaptiveFPSController::Config cfg;
  cfg.idle_fps = 10;
  cfg.active_fps = 30;
  cfg.ramp_up_frames = 1;
  cfg.ramp_down_frames = 10;
  neuro::pipeline::AdaptiveFPSController controller(cfg);

  // Ramp up first
  controller.Update(5);
  EXPECT_GE(controller.GetTargetFPS(), 20u);

  // Ramp down over several idle frames
  for (int i = 0; i < 20; ++i) {
    controller.Update(0);
  }
  EXPECT_EQ(controller.GetTargetFPS(), cfg.idle_fps);
}

TEST(AdaptiveFPSTest, ClampsToMinMax) {
  neuro::pipeline::AdaptiveFPSController::Config cfg;
  cfg.min_fps = 5;
  cfg.max_fps = 30;
  cfg.idle_fps = 10;
  cfg.active_fps = 30;
  cfg.ramp_up_frames = 1;
  cfg.ramp_down_frames = 1;
  neuro::pipeline::AdaptiveFPSController controller(cfg);

  // After detection, should not exceed max
  controller.Update(10);
  EXPECT_LE(controller.GetTargetFPS(), cfg.max_fps);

  // After idle, should not go below min
  controller.Update(0);
  EXPECT_GE(controller.GetTargetFPS(), cfg.min_fps);
}

TEST(AdaptiveFPSTest, ResetRestoresDefault) {
  neuro::pipeline::AdaptiveFPSController::Config cfg;
  cfg.idle_fps = 10;
  cfg.active_fps = 30;
  cfg.ramp_up_frames = 1;
  neuro::pipeline::AdaptiveFPSController controller(cfg);

  controller.Update(5);
  EXPECT_NE(controller.GetTargetFPS(), cfg.idle_fps);

  controller.Reset();
  EXPECT_EQ(controller.GetTargetFPS(), cfg.idle_fps);
}

}  // namespace
