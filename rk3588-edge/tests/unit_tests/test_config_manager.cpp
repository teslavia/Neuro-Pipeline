#include <gtest/gtest.h>

#include <cstdio>
#include <fstream>
#include <string>

#include "app/config_manager.hpp"

namespace {

// Helper: write a temp config file and return its path
std::string WriteTempConfig(const std::string& content) {
  std::string path = "/tmp/test_config_manager.yaml";
  std::ofstream f(path);
  f << content;
  f.close();
  return path;
}

TEST(ConfigManagerTest, NestedSections) {
  auto path = WriteTempConfig(
      "edge:\n"
      "  device_id: edge-001\n"
      "  recording:\n"
      "    enabled: true\n"
      "    pre_seconds: 10\n");
  app::ConfigManager cfg;
  ASSERT_TRUE(cfg.LoadFromFile(path));
  EXPECT_EQ(cfg.Get("edge.device_id"), "edge-001");
  EXPECT_EQ(cfg.Get("edge.recording.enabled"), "true");
  EXPECT_EQ(cfg.GetInt("edge.recording.pre_seconds"), 10);
}

TEST(ConfigManagerTest, ListItemsSingleLine) {
  // Flat list items (all on "- " lines)
  auto path = WriteTempConfig(
      "edge:\n"
      "  cameras:\n"
      "    - device: /dev/video0\n"
      "    - device: /dev/video1\n");
  app::ConfigManager cfg;
  ASSERT_TRUE(cfg.LoadFromFile(path));
  EXPECT_EQ(cfg.Get("edge.cameras.0.device"), "/dev/video0");
  EXPECT_EQ(cfg.Get("edge.cameras.1.device"), "/dev/video1");
}

TEST(ConfigManagerTest, MultiLineListItems) {
  // Multi-line list items: continuation lines after "- "
  auto path = WriteTempConfig(
      "edge:\n"
      "  models:\n"
      "    - model_id: yolov5s\n"
      "      model_path: /opt/models/yolov5s.rknn\n"
      "      postprocessor: yolov5\n"
      "      npu_core: 0\n"
      "    - model_id: yolov8s\n"
      "      model_path: /opt/models/yolov8s.rknn\n"
      "      postprocessor: yolov8\n"
      "      npu_core: 2\n");
  app::ConfigManager cfg;
  ASSERT_TRUE(cfg.LoadFromFile(path));

  // First model
  EXPECT_EQ(cfg.Get("edge.models.0.model_id"), "yolov5s");
  EXPECT_EQ(cfg.Get("edge.models.0.model_path"), "/opt/models/yolov5s.rknn");
  EXPECT_EQ(cfg.Get("edge.models.0.postprocessor"), "yolov5");
  EXPECT_EQ(cfg.GetInt("edge.models.0.npu_core"), 0);

  // Second model
  EXPECT_EQ(cfg.Get("edge.models.1.model_id"), "yolov8s");
  EXPECT_EQ(cfg.Get("edge.models.1.model_path"), "/opt/models/yolov8s.rknn");
  EXPECT_EQ(cfg.Get("edge.models.1.postprocessor"), "yolov8");
  EXPECT_EQ(cfg.GetInt("edge.models.1.npu_core"), 2);
}

TEST(ConfigManagerTest, ListFollowedByRegularKey) {
  // After list ends, regular keys should parse correctly
  auto path = WriteTempConfig(
      "edge:\n"
      "  models:\n"
      "    - model_id: yolov5s\n"
      "      model_path: /opt/yolov5s.rknn\n"
      "  fps: 30\n");
  app::ConfigManager cfg;
  ASSERT_TRUE(cfg.LoadFromFile(path));
  EXPECT_EQ(cfg.Get("edge.models.0.model_id"), "yolov5s");
  EXPECT_EQ(cfg.Get("edge.models.0.model_path"), "/opt/yolov5s.rknn");
  EXPECT_EQ(cfg.GetInt("edge.fps"), 30);
}

TEST(ConfigManagerTest, QuotedEmptyString) {
  auto path = WriteTempConfig(
      "edge:\n"
      "  ca_cert: \"\"\n"
      "  device_id: edge-001\n");
  app::ConfigManager cfg;
  ASSERT_TRUE(cfg.LoadFromFile(path));
  EXPECT_EQ(cfg.Get("edge.ca_cert"), "");
  EXPECT_TRUE(cfg.Has("edge.ca_cert"));
  EXPECT_EQ(cfg.Get("edge.device_id"), "edge-001");
}

}  // namespace
