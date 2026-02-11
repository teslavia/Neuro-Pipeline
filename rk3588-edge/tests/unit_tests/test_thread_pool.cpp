#include <gtest/gtest.h>

#include <atomic>
#include <numeric>
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

}  // namespace
