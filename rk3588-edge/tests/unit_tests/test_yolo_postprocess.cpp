#include <gtest/gtest.h>

#include "common/yolo_postprocess.hpp"

namespace {

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
      {0, "person", 0.8f, 0.12f, 0.12f, 0.52f, 0.52f},  // Overlaps with first
      {0, "person", 0.7f, 0.6f, 0.6f, 0.9f, 0.9f},       // No overlap
  };

  auto result = ai_inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);
  EXPECT_FLOAT_EQ(result[0].confidence, 0.9f);  // Highest confidence kept
  EXPECT_FLOAT_EQ(result[1].confidence, 0.7f);  // Non-overlapping kept
}

TEST_F(YOLOPostProcessTest, NMSPreservesDifferentClasses) {
  std::vector<common::DetectionBox> boxes = {
      {0, "person", 0.9f, 0.1f, 0.1f, 0.5f, 0.5f},
      {1, "car", 0.8f, 0.1f, 0.1f, 0.5f, 0.5f},  // Same box, different class
  };

  auto result = ai_inference::YOLOPostProcessor::NMS(boxes, 0.45f);
  EXPECT_EQ(result.size(), 2u);  // Both kept (different classes)
}

TEST_F(YOLOPostProcessTest, ProcessEmptyOutputReturnsEmpty) {
  ai_inference::YOLOPostProcessor processor(config_);
  std::vector<std::vector<float>> empty_outputs;
  auto result = processor.Process(empty_outputs, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

}  // namespace
