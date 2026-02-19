#include <gtest/gtest.h>
#include <thread>
#include <vector>
#include "neuro/comm/detection_queue.hpp"
#include "neuro_pipeline.pb.h"

using neuro::comm::DetectionQueue;

namespace {

neuro_pipeline::DetectionResult MakeResult(int id, float confidence = 0.9f) {
  neuro_pipeline::DetectionResult result;
  result.set_device_id("test-device");
  result.set_frame_number(id);
  auto* det = result.add_detections();
  det->set_class_name("person");
  det->set_confidence(confidence);
  det->mutable_bbox()->set_x(0.1f);
  det->mutable_bbox()->set_y(0.2f);
  det->mutable_bbox()->set_width(0.3f);
  det->mutable_bbox()->set_height(0.4f);
  return result;
}

}  // namespace

TEST(DetectionQueueTest, EnqueueDequeue) {
  DetectionQueue queue;
  auto result = MakeResult(1);
  EXPECT_TRUE(queue.Enqueue(result));
  EXPECT_EQ(queue.Size(), 1u);

  neuro_pipeline::DetectionResult out;
  EXPECT_TRUE(queue.Dequeue(&out));
  EXPECT_EQ(out.frame_number(), 1);
  EXPECT_TRUE(queue.Empty());
}

TEST(DetectionQueueTest, FIFOOrder) {
  DetectionQueue queue;
  for (int i = 0; i < 5; ++i) {
    queue.Enqueue(MakeResult(i));
  }
  EXPECT_EQ(queue.Size(), 5u);

  for (int i = 0; i < 5; ++i) {
    neuro_pipeline::DetectionResult out;
    EXPECT_TRUE(queue.Dequeue(&out));
    EXPECT_EQ(out.frame_number(), i);
  }
}

TEST(DetectionQueueTest, FullEviction) {
  DetectionQueue::Config cfg;
  cfg.max_entries = 3;
  DetectionQueue queue(cfg);

  for (int i = 0; i < 5; ++i) {
    queue.Enqueue(MakeResult(i));
  }
  // Should have evicted 0 and 1
  EXPECT_EQ(queue.Size(), 3u);
  EXPECT_EQ(queue.DroppedTotal(), 2u);

  neuro_pipeline::DetectionResult out;
  EXPECT_TRUE(queue.Dequeue(&out));
  EXPECT_EQ(out.frame_number(), 2);  // oldest surviving
}

TEST(DetectionQueueTest, MemoryLimit) {
  DetectionQueue::Config cfg;
  cfg.max_entries = 10000;
  cfg.max_memory_bytes = 200;  // very small
  DetectionQueue queue(cfg);

  // Each serialized result is ~50-80 bytes
  for (int i = 0; i < 10; ++i) {
    queue.Enqueue(MakeResult(i));
  }
  // Should have evicted some due to memory limit
  EXPECT_LT(queue.Size(), 10u);
  EXPECT_GT(queue.DroppedTotal(), 0u);
}

TEST(DetectionQueueTest, EmptyDequeue) {
  DetectionQueue queue;
  neuro_pipeline::DetectionResult out;
  EXPECT_FALSE(queue.Dequeue(&out));
  EXPECT_TRUE(queue.Empty());
}

TEST(DetectionQueueTest, ConcurrentAccess) {
  DetectionQueue queue;
  constexpr int kProducers = 4;
  constexpr int kPerProducer = 100;

  std::vector<std::thread> threads;
  for (int t = 0; t < kProducers; ++t) {
    threads.emplace_back([&queue, t]() {
      for (int i = 0; i < kPerProducer; ++i) {
        queue.Enqueue(MakeResult(t * kPerProducer + i));
      }
    });
  }
  for (auto& th : threads) th.join();

  EXPECT_EQ(queue.EnqueuedTotal(), kProducers * kPerProducer);
  EXPECT_EQ(queue.Size(), static_cast<size_t>(kProducers * kPerProducer));
}

TEST(DetectionQueueTest, StatsAccuracy) {
  DetectionQueue::Config cfg;
  cfg.max_entries = 2;
  DetectionQueue queue(cfg);

  queue.Enqueue(MakeResult(0));
  queue.Enqueue(MakeResult(1));
  queue.Enqueue(MakeResult(2));  // evicts 0

  EXPECT_EQ(queue.EnqueuedTotal(), 3u);
  EXPECT_EQ(queue.DroppedTotal(), 1u);
  EXPECT_EQ(queue.Size(), 2u);
}
