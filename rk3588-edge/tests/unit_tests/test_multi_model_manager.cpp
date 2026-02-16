#include <gtest/gtest.h>

#include <algorithm>
#include <string>
#include <vector>

#include "common/multi_model_manager.hpp"

namespace {

// Mock model path -- the mock HAL engine ignores the path but we need a string.
constexpr const char* kMockPath = "models/mock.rknn";

TEST(MultiModelManagerTest, LoadAndListModels) {
  ai_inference::MultiModelManager mgr(3);

  EXPECT_TRUE(mgr.LoadModel("yolov5s", kMockPath, 0));
  EXPECT_TRUE(mgr.LoadModel("yolov8n", kMockPath, 1));

  auto ids = mgr.ListModels();
  EXPECT_EQ(ids.size(), 2u);
  EXPECT_TRUE(std::find(ids.begin(), ids.end(), "yolov5s") != ids.end());
  EXPECT_TRUE(std::find(ids.begin(), ids.end(), "yolov8n") != ids.end());
}

TEST(MultiModelManagerTest, MaxModelsLimit) {
  ai_inference::MultiModelManager mgr(2);

  EXPECT_TRUE(mgr.LoadModel("m1", kMockPath, 0));
  EXPECT_TRUE(mgr.LoadModel("m2", kMockPath, 1));
  EXPECT_FALSE(mgr.LoadModel("m3", kMockPath, 2));
  EXPECT_EQ(mgr.ModelCount(), 2u);
}

TEST(MultiModelManagerTest, UnloadModel) {
  ai_inference::MultiModelManager mgr(3);

  EXPECT_TRUE(mgr.LoadModel("m1", kMockPath));
  EXPECT_TRUE(mgr.LoadModel("m2", kMockPath));
  EXPECT_EQ(mgr.ModelCount(), 2u);

  EXPECT_TRUE(mgr.UnloadModel("m1"));
  EXPECT_EQ(mgr.ModelCount(), 1u);
  EXPECT_EQ(mgr.GetModel("m1"), nullptr);
}

TEST(MultiModelManagerTest, SwitchActiveModel) {
  ai_inference::MultiModelManager mgr(3);

  mgr.LoadModel("m1", kMockPath, 0);
  mgr.LoadModel("m2", kMockPath, 1);

  // First loaded model becomes active by default.
  auto* active = mgr.GetActiveModel();
  ASSERT_NE(active, nullptr);
  EXPECT_EQ(active->model_id, "m1");

  EXPECT_TRUE(mgr.SwitchActiveModel("m2"));
  active = mgr.GetActiveModel();
  ASSERT_NE(active, nullptr);
  EXPECT_EQ(active->model_id, "m2");
}

TEST(MultiModelManagerTest, DuplicateModelId) {
  ai_inference::MultiModelManager mgr(3);

  EXPECT_TRUE(mgr.LoadModel("dup", kMockPath));
  EXPECT_FALSE(mgr.LoadModel("dup", kMockPath));
  EXPECT_EQ(mgr.ModelCount(), 1u);
}

}  // namespace
