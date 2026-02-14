#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <numeric>
#include <thread>
#include <vector>

#include "common/thread_pool.hpp"

namespace {

TEST(ThreadPoolTest, ConstructAndDestruct) {
  data_processing::ThreadPool pool(4);
  EXPECT_EQ(pool.Size(), 4u);
}

TEST(ThreadPoolTest, SubmitSingleTask) {
  data_processing::ThreadPool pool(2);
  auto future = pool.Submit([]() { return 42; });
  EXPECT_EQ(future.get(), 42);
}

TEST(ThreadPoolTest, SubmitMultipleTasks) {
  data_processing::ThreadPool pool(4);
  std::vector<std::future<int>> futures;

  for (int i = 0; i < 100; ++i) {
    futures.push_back(pool.Submit([i]() { return i * i; }));
  }

  for (int i = 0; i < 100; ++i) {
    EXPECT_EQ(futures[i].get(), i * i);
  }
}

TEST(ThreadPoolTest, ConcurrentAccess) {
  data_processing::ThreadPool pool(4);
  std::atomic<int> counter{0};
  std::vector<std::future<void>> futures;

  for (int i = 0; i < 1000; ++i) {
    futures.push_back(pool.Submit([&counter]() { counter.fetch_add(1); }));
  }

  for (auto& f : futures) {
    f.get();
  }

  EXPECT_EQ(counter.load(), 1000);
}

TEST(ThreadPoolTest, ShutdownIsIdempotent) {
  data_processing::ThreadPool pool(2);
  pool.Shutdown();
  pool.Shutdown();  // Should not crash
}

TEST(ThreadPoolTest, PendingTasksCount) {
  // Use 1 thread and block it so tasks queue up
  data_processing::ThreadPool pool(1);
  std::promise<void> blocker;
  auto block_future = blocker.get_future();

  // Submit a blocking task
  pool.Submit([&block_future]() { block_future.wait(); });

  // Submit more tasks that will queue
  auto f1 = pool.Submit([]() { return 1; });
  auto f2 = pool.Submit([]() { return 2; });

  // At least 1 task should be pending (the 2 non-blocking ones)
  EXPECT_GE(pool.PendingTasks(), 1u);

  // Unblock
  blocker.set_value();
  f1.get();
  f2.get();
}

TEST(ThreadPoolTest, MaxQueueSizeRejectsOverflow) {
  data_processing::ThreadPool pool(1, 2);  // max 2 queued tasks
  std::promise<void> blocker;
  auto block_future = blocker.get_future();

  // Block the worker
  pool.Submit([&block_future]() { block_future.wait(); });

  // Give worker time to dequeue the blocking task
  std::this_thread::sleep_for(std::chrono::milliseconds(50));

  // Fill the queue
  pool.Submit([]() {});
  pool.Submit([]() {});

  // Third should throw
  EXPECT_THROW(pool.Submit([]() {}), std::runtime_error);

  blocker.set_value();
  pool.Shutdown();
}

}  // namespace
