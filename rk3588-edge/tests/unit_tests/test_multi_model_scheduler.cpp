#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "neuro/inference/multi_model_manager.hpp"
#include "neuro/inference/multi_model_scheduler.hpp"

namespace {

constexpr const char* kMockPath = "models/mock.rknn";

TEST(MultiModelSchedulerTest, BindModelToCore) {
  neuro::inference::MultiModelManager mgr(3);
  mgr.LoadModel("yolov5s", kMockPath, 0);

  neuro::inference::MultiModelScheduler scheduler(mgr);
  EXPECT_TRUE(scheduler.BindModelToCore("yolov5s", 0));
  EXPECT_EQ(scheduler.GetBindings().size(), 1u);
  EXPECT_EQ(scheduler.GetBindings()[0].model_id, "yolov5s");
  EXPECT_EQ(scheduler.GetBindings()[0].npu_core, 0);
}

TEST(MultiModelSchedulerTest, BindInvalidCore) {
  neuro::inference::MultiModelManager mgr(3);
  mgr.LoadModel("yolov5s", kMockPath, 0);

  neuro::inference::MultiModelScheduler scheduler(mgr);
  EXPECT_FALSE(scheduler.BindModelToCore("yolov5s", 3));
  EXPECT_FALSE(scheduler.BindModelToCore("yolov5s", -1));
  EXPECT_EQ(scheduler.GetBindings().size(), 0u);
}

TEST(MultiModelSchedulerTest, InferParallelEmpty) {
  neuro::inference::MultiModelManager mgr(3);
  neuro::inference::MultiModelScheduler scheduler(mgr);

  auto frame = neuro::core::BufferFactory::CreateDMABuffer(640 * 640 * 3);
  auto results = scheduler.InferParallel(frame, 1920, 1080);
  EXPECT_TRUE(results.empty());
}

}  // namespace
