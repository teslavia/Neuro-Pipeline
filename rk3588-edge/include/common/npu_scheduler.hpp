#ifndef AI_INFERENCE_NPU_SCHEDULER_HPP_
#define AI_INFERENCE_NPU_SCHEDULER_HPP_

#include <atomic>
#include <cstdint>
#include <mutex>
#include <array>

namespace ai_inference {

/**
 * @brief NPU multi-core task scheduler for RK3588.
 *
 * Distributes inference tasks across RK3588's 3 NPU cores using
 * configurable scheduling strategies. Thread-safe for concurrent
 * inference submissions.
 *
 * RK3588 NPU core masks:
 *   Core 0 = 0x01 (1)
 *   Core 1 = 0x02 (2)
 *   Core 2 = 0x04 (4)
 *   All     = 0x07 (7) — fuses 3 cores for single model
 */
class NPUScheduler {
 public:
  /// Number of NPU cores on RK3588.
  static constexpr int kNumCores = 3;

  /// Core mask constants.
  static constexpr int kCore0 = 0x01;
  static constexpr int kCore1 = 0x02;
  static constexpr int kCore2 = 0x04;
  static constexpr int kAllCores = 0x07;

  enum class Strategy {
    kRoundRobin,   ///< Rotate across cores sequentially
    kLoadBalance,  ///< Pick the core with fewest active tasks
    kSingleCore,   ///< Use core 0 only
    kTripleCore,   ///< Fuse all 3 cores for one model (highest perf)
  };

  explicit NPUScheduler(Strategy strategy = Strategy::kRoundRobin);

  /// Select the next NPU core mask for inference submission.
  int SelectCore();

  /// Notify scheduler that a task started on the given core index (0-2).
  void NotifyTaskStart(int core_index);

  /// Notify scheduler that a task finished on the given core index (0-2).
  void NotifyTaskEnd(int core_index);

  /// Get the current active task count for a core (0-2).
  int ActiveTasks(int core_index) const;

  /// Get total tasks submitted since construction.
  uint64_t TotalSubmitted() const;

  /// Change scheduling strategy at runtime.
  void SetStrategy(Strategy strategy);

  /// Get current strategy.
  Strategy GetStrategy() const;

 private:
  int SelectRoundRobin();
  int SelectLoadBalance();

  static bool IsValidCoreIndex(int idx) { return idx >= 0 && idx < kNumCores; }
  static int CoreIndexToMask(int idx);

  Strategy strategy_;
  std::atomic<uint32_t> round_robin_counter_{0};
  std::atomic<uint64_t> total_submitted_{0};
  std::array<std::atomic<int>, kNumCores> active_tasks_;
  mutable std::mutex strategy_mutex_;
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_NPU_SCHEDULER_HPP_
