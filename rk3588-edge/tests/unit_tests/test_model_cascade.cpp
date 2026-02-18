#include <gtest/gtest.h>

#include <vector>

#include "common/model_cascade.hpp"
#include "common/types.hpp"

namespace ai_inference {
namespace {

// Helper to create a detection box
common::DetectionBox MakeDetection(uint32_t class_id, float confidence,
                                    float x_min, float y_min,
                                    float x_max, float y_max) {
  common::DetectionBox det;
  det.class_id = class_id;
  det.confidence = confidence;
  det.x_min = x_min;
  det.y_min = y_min;
  det.x_max = x_max;
  det.y_max = y_max;
  return det;
}

class ModelCascadeTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Default config for testing
    config_.light_model_id = "yolov5s";
    config_.heavy_model_id = "yolov8s";
    config_.min_confidence = 0.3f;
    config_.max_confidence = 0.7f;
    config_.min_detections = 1;
    config_.roi_padding = 0.1f;
    config_.max_cascade_per_frame = 5;
    config_.merge_results = true;
    config_.heavy_weight = 0.8f;
  }

  CascadeConfig config_;
};

// Test ShouldCascade with empty detections
TEST_F(ModelCascadeTest, ShouldCascade_EmptyDetections) {
  ModelCascade cascade(config_);
  std::vector<common::DetectionBox> empty;
  EXPECT_FALSE(cascade.ShouldCascade(empty));
}

// Test ShouldCascade with high confidence (no cascade needed)
TEST_F(ModelCascadeTest, ShouldCascade_HighConfidence) {
  ModelCascade cascade(config_);
  std::vector<common::DetectionBox> detections = {
      MakeDetection(0, 0.85f, 0.1f, 0.1f, 0.3f, 0.3f)  // High confidence
  };
  EXPECT_FALSE(cascade.ShouldCascade(detections));
}

// Test ShouldCascade with low confidence (cascade needed)
TEST_F(ModelCascadeTest, ShouldCascade_MediumConfidence) {
  ModelCascade cascade(config_);
  std::vector<common::DetectionBox> detections = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)  // Medium confidence
  };
  EXPECT_TRUE(cascade.ShouldCascade(detections));
}

// Test ShouldCascade with very low confidence (below threshold)
TEST_F(ModelCascadeTest, ShouldCascade_VeryLowConfidence) {
  ModelCascade cascade(config_);
  std::vector<common::DetectionBox> detections = {
      MakeDetection(0, 0.2f, 0.1f, 0.1f, 0.3f, 0.3f)  // Very low confidence
  };
  EXPECT_FALSE(cascade.ShouldCascade(detections));  // Below min_confidence
}

// Test ShouldCascade with class filtering
TEST_F(ModelCascadeTest, ShouldCascade_ClassFilter) {
  config_.target_classes = {0, 1};  // Only cascade for class 0 and 1
  ModelCascade cascade(config_);

  std::vector<common::DetectionBox> detections = {
      MakeDetection(2, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)  // Class 2, medium confidence
  };
  EXPECT_FALSE(cascade.ShouldCascade(detections));  // Filtered out by class
}

// Test ShouldCascade with min_detections requirement
TEST_F(ModelCascadeTest, ShouldCascade_MinDetections) {
  config_.min_detections = 2;
  ModelCascade cascade(config_);

  std::vector<common::DetectionBox> single = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)
  };
  EXPECT_FALSE(cascade.ShouldCascade(single));  // Only 1 detection

  std::vector<common::DetectionBox> multiple = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f),
      MakeDetection(0, 0.4f, 0.5f, 0.5f, 0.7f, 0.7f)
  };
  EXPECT_TRUE(cascade.ShouldCascade(multiple));  // 2 detections
}

// Test MergeDetections with overlapping boxes
TEST_F(ModelCascadeTest, MergeDetections_Overlapping) {
  ModelCascade cascade(config_);

  std::vector<common::DetectionBox> light = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)
  };
  std::vector<common::DetectionBox> heavy = {
      MakeDetection(0, 0.9f, 0.11f, 0.11f, 0.29f, 0.29f)  // Overlaps with light
  };

  auto merged = cascade.MergeDetections(light, heavy);

  // Heavy detection should have weighted confidence
  // Light detection should be suppressed due to overlap
  EXPECT_EQ(merged.size(), 1);
  EXPECT_NEAR(merged[0].confidence, 0.9f * 0.8f, 0.001f);  // heavy_weight applied
}

// Test MergeDetections with non-overlapping boxes
TEST_F(ModelCascadeTest, MergeDetections_NonOverlapping) {
  ModelCascade cascade(config_);

  std::vector<common::DetectionBox> light = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)
  };
  std::vector<common::DetectionBox> heavy = {
      MakeDetection(0, 0.9f, 0.6f, 0.6f, 0.8f, 0.8f)  // Far from light
  };

  auto merged = cascade.MergeDetections(light, heavy);

  // Both should be in merged result
  EXPECT_EQ(merged.size(), 2);
}

// Test MergeDetections with merge_results disabled
TEST_F(ModelCascadeTest, MergeDetections_NoMerge) {
  config_.merge_results = false;
  ModelCascade cascade(config_);

  std::vector<common::DetectionBox> light = {
      MakeDetection(0, 0.5f, 0.1f, 0.1f, 0.3f, 0.3f)
  };
  std::vector<common::DetectionBox> heavy = {
      MakeDetection(0, 0.9f, 0.6f, 0.6f, 0.8f, 0.8f)
  };

  auto merged = cascade.MergeDetections(light, heavy);

  // Only heavy results when merge is disabled
  EXPECT_EQ(merged.size(), 1);
  EXPECT_FLOAT_EQ(merged[0].confidence, 0.9f);  // No weight applied
}

// Test config access
TEST_F(ModelCascadeTest, ConfigAccess) {
  ModelCascade cascade(config_);
  const auto& cfg = cascade.GetConfig();

  EXPECT_EQ(cfg.light_model_id, "yolov5s");
  EXPECT_EQ(cfg.heavy_model_id, "yolov8s");
  EXPECT_FLOAT_EQ(cfg.min_confidence, 0.3f);
  EXPECT_FLOAT_EQ(cfg.max_confidence, 0.7f);
}

}  // namespace
}  // namespace ai_inference
