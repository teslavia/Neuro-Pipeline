#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "neuro/inference/yolo_postprocess.hpp"

namespace {

inline float InvSigmoid(float y) {
  return std::log(y / (1.0f - y));
}

class YOLOPostProcessTest : public ::testing::Test {
 protected:
  void SetUp() override {
    config_.confidence_threshold = 0.5f;
    config_.nms_threshold = 0.45f;
    config_.num_classes = 80;
    config_.input_width = 640;
    config_.input_height = 640;
  }
  neuro::inference::YOLOPostProcessor::Config config_{};
};

TEST_F(YOLOPostProcessTest, ComputeIoUIdenticalBoxes) {
  neuro::core::DetectionBox a{0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f};
  neuro::core::DetectionBox b = a;
  float iou = neuro::inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_FLOAT_EQ(iou, 1.0f);
}

TEST_F(YOLOPostProcessTest, ComputeIoUNoOverlap) {
  neuro::core::DetectionBox a{0, "person", 0.9f, 0.0f, 0.0f, 0.3f, 0.3f};
  neuro::core::DetectionBox b{0, "person", 0.8f, 0.5f, 0.5f, 0.8f, 0.8f};
  float iou = neuro::inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_FLOAT_EQ(iou, 0.0f);
}

TEST_F(YOLOPostProcessTest, ComputeIoUPartialOverlap) {
  neuro::core::DetectionBox a{0, "person", 0.9f, 0.0f, 0.0f, 0.4f, 0.4f};
  neuro::core::DetectionBox b{0, "person", 0.8f, 0.2f, 0.2f, 0.6f, 0.6f};
  float iou = neuro::inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_GT(iou, 0.0f);
  EXPECT_LT(iou, 1.0f);
}

TEST_F(YOLOPostProcessTest, NMSEmptyInput) {
  std::vector<neuro::core::DetectionBox> boxes;
  auto result = neuro::inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, NMSSuppressesOverlapping) {
  std::vector<neuro::core::DetectionBox> boxes = {
      {0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f},
      {0, "person", 0.8f, 0.12f, 0.12f, 0.52f, 0.52f},
      {0, "person", 0.7f, 0.6f, 0.6f, 0.9f, 0.9f},
  };

  auto result = neuro::inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);
  EXPECT_FLOAT_EQ(result[0].confidence, 0.9f);
  EXPECT_FLOAT_EQ(result[1].confidence, 0.7f);
}

TEST_F(YOLOPostProcessTest, NMSPreservesDifferentClasses) {
  std::vector<neuro::core::DetectionBox> boxes = {
      {0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f},
      {1, "car", 0.8f, 0.1f, 0.1f, 0.5f, 0.5f},
  };

  auto result = neuro::inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);
}

TEST_F(YOLOPostProcessTest, ProcessEmptyOutputReturnsEmpty) {
  neuro::inference::YOLOPostProcessor processor(config_);
  std::vector<std::vector<float>> empty_outputs;
  auto result = processor.Process(empty_outputs, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessWrongSizeOutputReturnsEmpty) {
  neuro::inference::YOLOPostProcessor processor(config_);
  // Wrong size tensor — should be skipped
  std::vector<std::vector<float>> bad_outputs = {{1.0f, 2.0f, 3.0f}};
  auto result = processor.Process(bad_outputs, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessDecodesHighConfidenceDetection) {
  // Construct a synthetic P3/8 output in RKNN NCHW format
  // Layout: (3_anchors × 85_channels) × grid_h × grid_w
  const int grid = 80;
  const int prop_size = 85;
  const int grid_len = grid * grid;
  const int total = 3 * prop_size * grid_len;

  std::vector<float> p3(total, 0.05f);  // Low values (post-sigmoid)

  // Place a high-confidence "person" at grid cell (20, 10), anchor 0
  int pos = 10 * grid + 20;  // y=10, x=20
  int base = 0 * prop_size * grid_len;  // anchor 0
  // NCHW: output[base + channel * grid_len + pos]
  p3[base + 0 * grid_len + pos] = 0.5f;  // bx (post-sigmoid)
  p3[base + 1 * grid_len + pos] = 0.5f;  // by
  p3[base + 2 * grid_len + pos] = 0.5f;  // bw
  p3[base + 3 * grid_len + pos] = 0.5f;  // bh
  p3[base + 4 * grid_len + pos] = 0.95f; // objectness
  p3[base + 5 * grid_len + pos] = 0.9f;  // class 0 (person)

  // P4 and P5 are all low confidence
  const int p4_total = 3 * prop_size * 40 * 40;
  const int p5_total = 3 * prop_size * 20 * 20;
  std::vector<float> p4(p4_total, 0.05f);
  std::vector<float> p5(p5_total, 0.05f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  neuro::inference::YOLOPostProcessor processor(config_);
  auto result = processor.Process(outputs, 640, 640);

  ASSERT_GE(result.size(), 1u);
  EXPECT_EQ(result[0].class_id, 0u);
  EXPECT_EQ(result[0].class_name, "person");
  EXPECT_GT(result[0].confidence, 0.8f);

  // Check bbox is in valid range [0, 1]
  EXPECT_GE(result[0].x_min, 0.0f);
  EXPECT_LE(result[0].x_max, 1.0f);
  EXPECT_GE(result[0].y_min, 0.0f);
  EXPECT_LE(result[0].y_max, 1.0f);
  EXPECT_LT(result[0].x_min, result[0].x_max);
  EXPECT_LT(result[0].y_min, result[0].y_max);
}

TEST_F(YOLOPostProcessTest, ProcessFiltersLowConfidence) {
  const int grid = 80;
  const int prop_size = 85;
  const int grid_len = grid * grid;

  // All entries have very low values (post-sigmoid)
  std::vector<float> p3(3 * prop_size * grid_len, 0.01f);
  std::vector<float> p4(3 * prop_size * 40 * 40, 0.01f);
  std::vector<float> p5(3 * prop_size * 20 * 20, 0.01f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  neuro::inference::YOLOPostProcessor processor(config_);
  auto result = processor.Process(outputs, 640, 640);

  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessScalesToOriginalImage) {
  const int grid = 80;
  const int prop_size = 85;
  const int grid_len = grid * grid;

  std::vector<float> p3(3 * prop_size * grid_len, 0.05f);

  // Place detection at center of grid (40, 40)
  int pos = 40 * grid + 40;
  int base = 0 * prop_size * grid_len;
  p3[base + 0 * grid_len + pos] = 0.5f;
  p3[base + 1 * grid_len + pos] = 0.5f;
  p3[base + 2 * grid_len + pos] = 0.5f;
  p3[base + 3 * grid_len + pos] = 0.5f;
  p3[base + 4 * grid_len + pos] = 0.95f;
  p3[base + 5 * grid_len + pos] = 0.9f;

  std::vector<float> p4(3 * prop_size * 40 * 40, 0.05f);
  std::vector<float> p5(3 * prop_size * 20 * 20, 0.05f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  neuro::inference::YOLOPostProcessor processor(config_);

  // Process with 1920×1080 original image
  auto result = processor.Process(outputs, 1920, 1080);
  ASSERT_GE(result.size(), 1u);

  // Detection should be roughly centered
  float cx = (result[0].x_min + result[0].x_max) / 2.0f;
  float cy = (result[0].y_min + result[0].y_max) / 2.0f;
  EXPECT_NEAR(cx, 0.5f, 0.05f);
  EXPECT_NEAR(cy, 0.5f, 0.05f);
}

}  // namespace
