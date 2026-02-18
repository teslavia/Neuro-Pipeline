#include "neuro/inference/npu_scheduler.hpp"

#include <algorithm>
#include <limits>

namespace neuro::inference {

NPUScheduler::NPUScheduler(Strategy strategy) : strategy_(strategy) {
  for (auto& count : active_tasks_) {
    count.store(0, std::memory_order_relaxed);
  }
}

int NPUScheduler::CoreIndexToMask(int idx) {
  // Core 0 → 0x01, Core 1 → 0x02, Core 2 → 0x04
  return 1 << idx;
}

int NPUScheduler::SelectCore() {
  total_submitted_.fetch_add(1, std::memory_order_relaxed);

  std::lock_guard<std::mutex> lock(strategy_mutex_);
  switch (strategy_) {
    case Strategy::kRoundRobin:
      return SelectRoundRobin();
    case Strategy::kLoadBalance:
      return SelectLoadBalance();
    case Strategy::kSingleCore:
      return kCore0;
    case Strategy::kTripleCore:
      return kAllCores;
    default:
      return kCore0;
  }
}

int NPUScheduler::SelectRoundRobin() {
  uint32_t idx = round_robin_counter_.fetch_add(1, std::memory_order_relaxed);
  return CoreIndexToMask(idx % kNumCores);
}

int NPUScheduler::SelectLoadBalance() {
  int min_load = std::numeric_limits<int>::max();
  int best_core = 0;

  for (int i = 0; i < kNumCores; ++i) {
    int load = active_tasks_[i].load(std::memory_order_relaxed);
    if (load < min_load) {
      min_load = load;
      best_core = i;
    }
  }

  return CoreIndexToMask(best_core);
}

void NPUScheduler::NotifyTaskStart(int core_index) {
  if (IsValidCoreIndex(core_index)) {
    active_tasks_[core_index].fetch_add(1, std::memory_order_relaxed);
  }
}

void NPUScheduler::NotifyTaskEnd(int core_index) {
  if (IsValidCoreIndex(core_index)) {
    active_tasks_[core_index].fetch_sub(1, std::memory_order_relaxed);
  }
}

int NPUScheduler::ActiveTasks(int core_index) const {
  if (!IsValidCoreIndex(core_index)) return 0;
  return active_tasks_[core_index].load(std::memory_order_relaxed);
}

uint64_t NPUScheduler::TotalSubmitted() const {
  return total_submitted_.load(std::memory_order_relaxed);
}

void NPUScheduler::SetStrategy(Strategy strategy) {
  std::lock_guard<std::mutex> lock(strategy_mutex_);
  strategy_ = strategy;
}

NPUScheduler::Strategy NPUScheduler::GetStrategy() const {
  std::lock_guard<std::mutex> lock(strategy_mutex_);
  return strategy_;
}

}  // namespace ai_inference
