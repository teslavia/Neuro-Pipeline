#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "neuro/inference/yolov8_postprocess.hpp"

namespace {

class YOLOv8PostProcessTest : public ::testing::Test {
 protected:
  void SetUp() override {
    config_.confidence_threshold = 0.5f;
    config_.nms_threshold = 0.45f;
    config_.num_classes = 80;
    config_.input_width = 640;
    config_.input_height = 640;
    config_.dfl_len = 16;
  }
  neuro::inference::YOLOv8PostProcessor::Config config_{};
};

TEST_F(YOLOv8PostProcessTest, ProcessEmptyOutputReturnsEmpty) {
  neuro::inference::YOLOv8PostProcessor processor(config_);
  std::vector<std::vector<float>> empty;
  auto result = processor.Process(empty, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOv8PostProcessTest, ProcessSingleOutputReturnsEmpty) {
  // Only 1 tensor — need at least 6 (2 per scale)
  neuro::inference::YOLOv8PostProcessor processor(config_);
  std::vector<std::vector<float>> one = {{1.0f}};
  auto result = processor.Process(one, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOv8PostProcessTest, ProcessWrongSizeTensorsReturnsEmpty) {
  neuro::inference::YOLOv8PostProcessor processor(config_);
  // 6 tensors but wrong sizes
  std::vector<std::vector<float>> bad(6, {1.0f, 2.0f});
  auto result = processor.Process(bad, 1920, 1080);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOv8PostProcessTest, ProcessFiltersLowConfidence) {
  neuro::inference::YOLOv8PostProcessor processor(config_);

  const int dfl_len = 16;
  const int nc = 80;
  // 6 tensors: box + score for each of 3 scales
  // Scale 0 (stride 8): grid 80×80
  int grid0 = 80 * 80;
  std::vector<float> box0(dfl_len * 4 * grid0, 0.0f);
  std::vector<float> score0(nc * grid0, 0.1f);  // All below threshold

  int grid1 = 40 * 40;
  std::vector<float> box1(dfl_len * 4 * grid1, 0.0f);
  std::vector<float> score1(nc * grid1, 0.1f);

  int grid2 = 20 * 20;
  std::vector<float> box2(dfl_len * 4 * grid2, 0.0f);
  std::vector<float> score2(nc * grid2, 0.1f);

  std::vector<std::vector<float>> outputs = {box0, score0, box1, score1,
                                              box2, score2};
  auto result = processor.Process(outputs, 640, 640);
  EXPECT_TRUE(result.empty());
}

TEST_F(YOLOv8PostProcessTest, ProcessDecodesHighConfidenceDetection) {
  neuro::inference::YOLOv8PostProcessor processor(config_);

  const int dfl_len = 16;
  const int nc = 80;

  // Scale 0 (stride 8): grid 80×80
  int grid_w = 80, grid_h = 80;
  int grid_len = grid_w * grid_h;
  std::vector<float> box0(dfl_len * 4 * grid_len, 0.0f);
  std::vector<float> score0(nc * grid_len, 0.0f);

  // Place a high-confidence "person" (class 0) at grid cell (40, 40)
  int pos = 40 * grid_w + 40;
  score0[0 * grid_len + pos] = 0.9f;  // class 0 = person

  // Set DFL box values: uniform distribution centered at index 8
  // This gives box offset ~8 for each of the 4 coordinates
  for (int b = 0; b < 4; ++b) {
    for (int d = 0; d < dfl_len; ++d) {
      // Peak at d=8 (center of distribution)
      float val = (d == 8) ? 5.0f : 0.0f;
      box0[(b * dfl_len + d) * grid_len + pos] = val;
    }
  }

  // Other scales: empty
  int grid1 = 40 * 40;
  std::vector<float> box1(dfl_len * 4 * grid1, 0.0f);
  std::vector<float> score1(nc * grid1, 0.0f);
  int grid2 = 20 * 20;
  std::vector<float> box2(dfl_len * 4 * grid2, 0.0f);
  std::vector<float> score2(nc * grid2, 0.0f);

  std::vector<std::vector<float>> outputs = {box0, score0, box1, score1,
                                              box2, score2};
  auto result = processor.Process(outputs, 640, 640);

  ASSERT_GE(result.size(), 1u);
  EXPECT_EQ(result[0].class_id, 0u);
  EXPECT_EQ(result[0].class_name, "person");
  EXPECT_GT(result[0].confidence, 0.8f);

  // Bbox should be in valid [0, 1] range
  EXPECT_GE(result[0].x_min, 0.0f);
  EXPECT_LE(result[0].x_max, 1.0f);
  EXPECT_GE(result[0].y_min, 0.0f);
  EXPECT_LE(result[0].y_max, 1.0f);
  EXPECT_LT(result[0].x_min, result[0].x_max);
  EXPECT_LT(result[0].y_min, result[0].y_max);
}

TEST_F(YOLOv8PostProcessTest, NameReturnsYOLOv8) {
  neuro::inference::YOLOv8PostProcessor processor(config_);
  EXPECT_EQ(processor.Name(), "YOLOv8");
}

}  // namespace
