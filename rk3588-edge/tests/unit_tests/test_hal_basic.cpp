#include <gtest/gtest.h>
#include "rk_hal/v4l2_camera.hpp"
#include "rk_hal/drm_allocator.hpp"

using namespace rk_hal;

TEST(HALBasic, V4L2CameraConfig) {
  V4L2Camera::Config cfg;
  cfg.device_path = "/dev/video0";
  cfg.width = 1920;
  cfg.height = 1080;

  EXPECT_EQ(cfg.device_path, "/dev/video0");
  EXPECT_EQ(cfg.width, 1920u);
  EXPECT_EQ(cfg.height, 1080u);
}

#ifdef USE_MOCK_HAL
TEST(HALBasic, V4L2MockInit) {
  V4L2Camera::Config cfg;
  cfg.device_path = "/dev/video0";
  cfg.width = 1920;
  cfg.height = 1080;

  V4L2Camera cam(cfg);
  EXPECT_TRUE(cam.Initialize());
}

TEST(HALBasic, DRMAllocatorMock) {
  DRMAllocator alloc;
  EXPECT_TRUE(alloc.Initialize());

  auto buf = alloc.Allocate(640 * 480 * 3);
  EXPECT_NE(buf, nullptr);
  EXPECT_GT(buf->Size(), 0u);
}
#endif
