#include <gtest/gtest.h>

#include <set>
#include <thread>
#include <vector>

#include "common/npu_scheduler.hpp"

namespace {

class NPUSchedulerTest : public ::testing::Test {
 protected:
  static constexpr int kCore0 = ai_inference::NPUScheduler::kCore0;
  static constexpr int kCore1 = ai_inference::NPUScheduler::kCore1;
  static constexpr int kCore2 = ai_inference::NPUScheduler::kCore2;
  static constexpr int kAllCores = ai_inference::NPUScheduler::kAllCores;
};

// ---- Construction ----

TEST_F(NPUSchedulerTest, DefaultStrategyIsRoundRobin) {
  ai_inference::NPUScheduler sched;
  EXPECT_EQ(sched.GetStrategy(),
            ai_inference::NPUScheduler::Strategy::kRoundRobin);
  EXPECT_EQ(sched.TotalSubmitted(), 0u);
}

TEST_F(NPUSchedulerTest, InitialActiveTasksAreZero) {
  ai_inference::NPUScheduler sched;
  for (int i = 0; i < ai_inference::NPUScheduler::kNumCores; ++i) {
    EXPECT_EQ(sched.ActiveTasks(i), 0);
  }
}

// ---- Round Robin ----

TEST_F(NPUSchedulerTest, RoundRobinCyclesThroughCores) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kRoundRobin);

  // First cycle
  EXPECT_EQ(sched.SelectCore(), kCore0);
  EXPECT_EQ(sched.SelectCore(), kCore1);
  EXPECT_EQ(sched.SelectCore(), kCore2);

  // Second cycle wraps around
  EXPECT_EQ(sched.SelectCore(), kCore0);
  EXPECT_EQ(sched.SelectCore(), kCore1);
  EXPECT_EQ(sched.SelectCore(), kCore2);
}

TEST_F(NPUSchedulerTest, RoundRobinOnlyProducesValidMasks) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kRoundRobin);

  std::set<int> valid_masks = {kCore0, kCore1, kCore2};
  for (int i = 0; i < 100; ++i) {
    int mask = sched.SelectCore();
    EXPECT_TRUE(valid_masks.count(mask) > 0)
        << "Invalid core mask: " << mask;
  }
}

// ---- Single Core ----

TEST_F(NPUSchedulerTest, SingleCoreAlwaysReturnsCore0) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kSingleCore);

  for (int i = 0; i < 10; ++i) {
    EXPECT_EQ(sched.SelectCore(), kCore0);
  }
}

// ---- Triple Core ----

TEST_F(NPUSchedulerTest, TripleCoreAlwaysReturnsAllCores) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kTripleCore);

  for (int i = 0; i < 10; ++i) {
    EXPECT_EQ(sched.SelectCore(), kAllCores);
  }
}

// ---- Load Balance ----

TEST_F(NPUSchedulerTest, LoadBalancePicksLeastLoaded) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kLoadBalance);

  // All idle → should pick core 0 (first with min load)
  EXPECT_EQ(sched.SelectCore(), kCore0);

  // Load core 0 with 3 tasks, core 1 with 1 task, core 2 idle
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(1);

  // Core 2 has 0 tasks → should be selected
  EXPECT_EQ(sched.SelectCore(), kCore2);
}

TEST_F(NPUSchedulerTest, LoadBalanceUpdatesAfterTaskEnd) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kLoadBalance);

  // Load cores 1 and 2
  sched.NotifyTaskStart(1);
  sched.NotifyTaskStart(1);
  sched.NotifyTaskStart(2);

  // Core 0 is least loaded (0 tasks)
  EXPECT_EQ(sched.SelectCore(), kCore0);

  // Now load core 0 heavily and free core 1
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(0);
  sched.NotifyTaskEnd(1);
  sched.NotifyTaskEnd(1);

  // Core 1 now has 0 tasks → should be selected
  EXPECT_EQ(sched.SelectCore(), kCore1);
}

TEST_F(NPUSchedulerTest, LoadBalanceTieBreaksToLowestIndex) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kLoadBalance);

  // All cores at equal load
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(1);
  sched.NotifyTaskStart(2);

  // Tie → first core (index 0) wins
  EXPECT_EQ(sched.SelectCore(), kCore0);
}

// ---- Task Tracking ----

TEST_F(NPUSchedulerTest, NotifyTaskStartIncrements) {
  ai_inference::NPUScheduler sched;

  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(0);
  sched.NotifyTaskStart(2);

  EXPECT_EQ(sched.ActiveTasks(0), 2);
  EXPECT_EQ(sched.ActiveTasks(1), 0);
  EXPECT_EQ(sched.ActiveTasks(2), 1);
}

TEST_F(NPUSchedulerTest, NotifyTaskEndDecrements) {
  ai_inference::NPUScheduler sched;

  sched.NotifyTaskStart(1);
  sched.NotifyTaskStart(1);
  sched.NotifyTaskStart(1);
  sched.NotifyTaskEnd(1);

  EXPECT_EQ(sched.ActiveTasks(1), 2);
}

TEST_F(NPUSchedulerTest, InvalidCoreIndexIsIgnored) {
  ai_inference::NPUScheduler sched;

  // Out-of-range indices should be silently ignored
  sched.NotifyTaskStart(-1);
  sched.NotifyTaskStart(3);
  sched.NotifyTaskEnd(-1);
  sched.NotifyTaskEnd(3);

  // No crashes, all counters at 0
  for (int i = 0; i < ai_inference::NPUScheduler::kNumCores; ++i) {
    EXPECT_EQ(sched.ActiveTasks(i), 0);
  }
  EXPECT_EQ(sched.ActiveTasks(-1), 0);
  EXPECT_EQ(sched.ActiveTasks(99), 0);
}

// ---- TotalSubmitted Counter ----

TEST_F(NPUSchedulerTest, TotalSubmittedIncrementsOnSelect) {
  ai_inference::NPUScheduler sched;
  EXPECT_EQ(sched.TotalSubmitted(), 0u);

  sched.SelectCore();
  sched.SelectCore();
  sched.SelectCore();

  EXPECT_EQ(sched.TotalSubmitted(), 3u);
}

// ---- Strategy Switch ----

TEST_F(NPUSchedulerTest, SetStrategyChangesAtRuntime) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kRoundRobin);

  EXPECT_EQ(sched.GetStrategy(),
            ai_inference::NPUScheduler::Strategy::kRoundRobin);

  sched.SetStrategy(ai_inference::NPUScheduler::Strategy::kTripleCore);
  EXPECT_EQ(sched.GetStrategy(),
            ai_inference::NPUScheduler::Strategy::kTripleCore);
  EXPECT_EQ(sched.SelectCore(), kAllCores);

  sched.SetStrategy(ai_inference::NPUScheduler::Strategy::kSingleCore);
  EXPECT_EQ(sched.SelectCore(), kCore0);
}

// ---- Concurrency ----

TEST_F(NPUSchedulerTest, ConcurrentSelectCoreIsThreadSafe) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kRoundRobin);

  constexpr int kThreads = 4;
  constexpr int kIterations = 1000;
  std::vector<std::thread> threads;

  for (int t = 0; t < kThreads; ++t) {
    threads.emplace_back([&sched]() {
      std::set<int> valid = {kCore0, kCore1, kCore2};
      for (int i = 0; i < kIterations; ++i) {
        int mask = sched.SelectCore();
        EXPECT_TRUE(valid.count(mask) > 0);
      }
    });
  }

  for (auto& th : threads) {
    th.join();
  }

  EXPECT_EQ(sched.TotalSubmitted(),
            static_cast<uint64_t>(kThreads * kIterations));
}

TEST_F(NPUSchedulerTest, ConcurrentLoadBalanceIsThreadSafe) {
  ai_inference::NPUScheduler sched(
      ai_inference::NPUScheduler::Strategy::kLoadBalance);

  constexpr int kThreads = 4;
  constexpr int kIterations = 500;
  std::vector<std::thread> threads;

  for (int t = 0; t < kThreads; ++t) {
    threads.emplace_back([&sched, t]() {
      int core = t % ai_inference::NPUScheduler::kNumCores;
      for (int i = 0; i < kIterations; ++i) {
        sched.NotifyTaskStart(core);
        sched.SelectCore();
        sched.NotifyTaskEnd(core);
      }
    });
  }

  for (auto& th : threads) {
    th.join();
  }

  // All tasks ended → all active counts should be 0
  for (int i = 0; i < ai_inference::NPUScheduler::kNumCores; ++i) {
    EXPECT_EQ(sched.ActiveTasks(i), 0);
  }
}

}  // namespace
