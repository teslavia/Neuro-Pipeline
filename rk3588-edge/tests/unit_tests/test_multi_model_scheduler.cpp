#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "common/multi_model_manager.hpp"
#include "common/multi_model_scheduler.hpp"

namespace {

constexpr const char* kMockPath = "models/mock.rknn";

TEST(MultiModelSchedulerTest, BindModelToCore) {
  ai_inference::MultiModelManager mgr(3);
  mgr.LoadModel("yolov5s", kMockPath, 0);

  ai_inference::MultiModelScheduler scheduler(mgr);
  EXPECT_TRUE(scheduler.BindModelToCore("yolov5s", 0));
  EXPECT_EQ(scheduler.GetBindings().size(), 1u);
  EXPECT_EQ(scheduler.GetBindings()[0].model_id, "yolov5s");
  EXPECT_EQ(scheduler.GetBindings()[0].npu_core, 0);
}

TEST(MultiModelSchedulerTest, BindInvalidCore) {
  ai_inference::MultiModelManager mgr(3);
  mgr.LoadModel("yolov5s", kMockPath, 0);

  ai_inference::MultiModelScheduler scheduler(mgr);
  EXPECT_FALSE(scheduler.BindModelToCore("yolov5s", 3));
  EXPECT_FALSE(scheduler.BindModelToCore("yolov5s", -1));
  EXPECT_EQ(scheduler.GetBindings().size(), 0u);
}

TEST(MultiModelSchedulerTest, InferParallelEmpty) {
  ai_inference::MultiModelManager mgr(3);
  ai_inference::MultiModelScheduler scheduler(mgr);

  auto frame = common::BufferFactory::CreateDMABuffer(640 * 640 * 3);
  auto results = scheduler.InferParallel(frame, 1920, 1080);
  EXPECT_TRUE(results.empty());
}

}  // namespace
