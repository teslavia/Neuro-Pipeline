#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "common/yolo_postprocess.hpp"

namespace {

inline float InvSigmoid(float y) {
  return std::log(y / (1.0f - y));
}

class YOLOPostProcessTest : public ::testing::Test {
 protected:
  ai_inference::YOLOPostProcessor::Config config_{
      .confidence_threshold = 0.5f,
      .nms_threshold = 0.45f,
      .num_classes = 80,
      .input_width = 640,
      .input_height = 640,
  };
};

TEST_F(YOLOPostProcessTest, ComputeIoUIdenticalBoxes) {
  common::DetectionBox a{0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f};
  common::DetectionBox b = a;
  float iou = ai_inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_FLOAT_EQ(iou, 1.0f);
}

TEST_F(YOLOPostProcessTest, ComputeIoUNoOverlap) {
  common::DetectionBox a{0, "person", 0.9f, 0.0f, 0.0f, 0.3f, 0.3f};
  common::DetectionBox b{0, "person", 0.8f, 0.5f, 0.5f, 0.8f, 0.8f};
  float iou = ai_inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_FLOAT_EQ(iou, 0.0f);
}

TEST_F(YOLOPostProcessTest, ComputeIoUPartialOverlap) {
  common::DetectionBox a{0, "person", 0.9f, 0.0f, 0.0f, 0.4f, 0.4f};
  common::DetectionBox b{0, "person", 0.8f, 0.2f, 0.2f, 0.6f, 0.6f};
  float iou = ai_inference::YOLOPostProcessor::ComputeIoU(a, b);
  EXPECT_GT(iou, 0.0f);
  EXPECT_LT(iou, 1.0f);
}

TEST_F(YOLOPostProcessTest, NMSEmptyInput) {
  std::vector<common::DetectionBox> boxes;
  auto result = ai_inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, NMSSuppressesOverlapping) {
  std::vector<common::DetectionBox> boxes = {
      {0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f},
      {0, "person", 0.8f, 0.12f, 0.12f, 0.52f, 0.52f},
      {0, "person", 0.7f, 0.6f, 0.6f, 0.9f, 0.9f},
  };

  auto result = ai_inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);
  EXPECT_FLOAT_EQ(result[0].confidence, 0.9f);
  EXPECT_FLOAT_EQ(result[1].confidence, 0.7f);
}

TEST_F(YOLOPostProcessTest, NMSPreservesDifferentClasses) {
  std::vector<common::DetectionBox> boxes = {
      {0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f},
      {1, "car", 0.8f, 0.1f, 0.1f, 0.5f, 0.5f},
  };

  auto result = ai_inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);
}

TEST_F(YOLOPostProcessTest, ProcessEmptyOutputReturnsEmpty) {
  ai_inference::YOLOPostProcessor processor(config_);
  std::vector<std::vector<float>> empty_outputs;
  auto result = processor.Process(empty_outputs, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessWrongSizeOutputReturnsEmpty) {
  ai_inference::YOLOPostProcessor processor(config_);
  // Wrong size tensor — should be skipped
  std::vector<std::vector<float>> bad_outputs = {{1.0f, 2.0f, 3.0f}};
  auto result = processor.Process(bad_outputs, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessDecodesHighConfidenceDetection) {
  // Construct a synthetic P3/8 output (80×80 grid, 3 anchors, 85 entries)
  const int grid = 80;
  const int entry_size = 85;
  const int total = grid * grid * 3 * entry_size;

  std::vector<float> p3(total, -5.0f);  // All low confidence

  // Place a high-confidence "person" (class 0) at grid cell (10, 20), anchor 0
  int idx = ((10 * grid + 20) * 3 + 0) * entry_size;
  p3[idx + 0] = InvSigmoid(0.5f);  // cx offset → center of cell
  p3[idx + 1] = InvSigmoid(0.5f);  // cy offset → center of cell
  p3[idx + 2] = InvSigmoid(0.5f);  // w scale → 1.0 × anchor_w
  p3[idx + 3] = InvSigmoid(0.5f);  // h scale → 1.0 × anchor_h
  p3[idx + 4] = InvSigmoid(0.95f); // objectness = 0.95
  p3[idx + 5] = InvSigmoid(0.9f);  // class 0 (person) = 0.9

  // P4 and P5 are all low confidence
  const int p4_total = 40 * 40 * 3 * entry_size;
  const int p5_total = 20 * 20 * 3 * entry_size;
  std::vector<float> p4(p4_total, -5.0f);
  std::vector<float> p5(p5_total, -5.0f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  ai_inference::YOLOPostProcessor processor(config_);
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
  const int entry_size = 85;
  const int total = grid * grid * 3 * entry_size;

  // All entries have very low objectness
  std::vector<float> p3(total, -10.0f);
  const int p4_total = 40 * 40 * 3 * entry_size;
  const int p5_total = 20 * 20 * 3 * entry_size;
  std::vector<float> p4(p4_total, -10.0f);
  std::vector<float> p5(p5_total, -10.0f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  ai_inference::YOLOPostProcessor processor(config_);
  auto result = processor.Process(outputs, 640, 640);

  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOPostProcessTest, ProcessScalesToOriginalImage) {
  const int grid = 80;
  const int entry_size = 85;
  const int total = grid * grid * 3 * entry_size;

  std::vector<float> p3(total, -5.0f);

  // Place detection at center of grid
  int idx = ((40 * grid + 40) * 3 + 0) * entry_size;
  p3[idx + 0] = InvSigmoid(0.5f);
  p3[idx + 1] = InvSigmoid(0.5f);
  p3[idx + 2] = InvSigmoid(0.5f);
  p3[idx + 3] = InvSigmoid(0.5f);
  p3[idx + 4] = InvSigmoid(0.95f);
  p3[idx + 5] = InvSigmoid(0.9f);

  const int p4_total = 40 * 40 * 3 * entry_size;
  const int p5_total = 20 * 20 * 3 * entry_size;
  std::vector<float> p4(p4_total, -5.0f);
  std::vector<float> p5(p5_total, -5.0f);

  std::vector<std::vector<float>> outputs = {p3, p4, p5};

  ai_inference::YOLOPostProcessor processor(config_);

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
