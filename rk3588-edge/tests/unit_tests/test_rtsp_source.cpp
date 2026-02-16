#include <gtest/gtest.h>
#include "rk_hal/rtsp_source.hpp"

TEST(RTSPSourceTest, InitializeAndCapture) {
  rk_hal::RTSPSource::Config cfg;
  cfg.url = "rtsp://192.168.1.100:8554/stream";
  cfg.width = 640;
  cfg.height = 480;

  rk_hal::RTSPSource source(cfg);
  EXPECT_TRUE(source.Initialize());
  EXPECT_TRUE(source.IsOpen());
  EXPECT_TRUE(source.Start());

  auto frame = source.CaptureFrame();
  EXPECT_NE(frame, nullptr);
  EXPECT_EQ(frame->Size(), 640u * 480u * 3u);

  source.ReleaseFrame(frame);
  source.Stop();
}

TEST(RTSPSourceTest, CaptureWithoutStart) {
  rk_hal::RTSPSource::Config cfg;
  cfg.url = "rtsp://localhost/test";
  cfg.width = 320;
  cfg.height = 240;

  rk_hal::RTSPSource source(cfg);
  EXPECT_TRUE(source.Initialize());
  // Don't call Start()
  auto frame = source.CaptureFrame();
  EXPECT_EQ(frame, nullptr);
}

TEST(RTSPSourceTest, Dimensions) {
  rk_hal::RTSPSource::Config cfg;
  cfg.url = "rtsp://localhost/test";
  cfg.width = 1920;
  cfg.height = 1080;

  rk_hal::RTSPSource source(cfg);
  EXPECT_EQ(source.Width(), 1920u);
  EXPECT_EQ(source.Height(), 1080u);
}

TEST(RTSPSourceTest, MultipleFrames) {
  rk_hal::RTSPSource::Config cfg;
  cfg.url = "rtsp://localhost/test";
  cfg.width = 320;
  cfg.height = 240;

  rk_hal::RTSPSource source(cfg);
  source.Initialize();
  source.Start();

  for (int i = 0; i < 5; ++i) {
    auto frame = source.CaptureFrame();
    EXPECT_NE(frame, nullptr);
    source.ReleaseFrame(frame);
  }
  source.Stop();
}
