#include <cstdint>
#include <memory>
#include <string>

// TODO: Include RKNN headers when available
// #include "rknn_api.h"

namespace ai_inference {

/**
 * @brief NPU multi-core task scheduler (mock/simplified).
 *
 * Distributes inference tasks across RK3588's 3 NPU cores
 * for load balancing and maximum throughput.
 */
class NPUScheduler {
 public:
  enum class Strategy {
    kRoundRobin,   // Rotate across cores
    kLoadBalance,  // Pick least loaded core
    kSingleCore,   // Use one core only
    kTripleCore,   // Use all 3 cores for one model (highest perf)
  };

  explicit NPUScheduler(Strategy strategy = Strategy::kRoundRobin)
      : strategy_(strategy), current_core_(0) {}

  /// Select next NPU core mask for inference.
  int SelectCore() {
    switch (strategy_) {
      case Strategy::kRoundRobin: {
        // RK3588 has 3 NPU cores: mask 1, 2, 4
        int masks[] = {1, 2, 4};
        int core = masks[current_core_ % 3];
        current_core_++;
        return core;
      }
      case Strategy::kTripleCore:
        return 7;  // All 3 cores (1|2|4)
      case Strategy::kSingleCore:
        return 1;  // Core 0 only
      case Strategy::kLoadBalance:
        // TODO: Read /sys/kernel/debug/rknpu/load and select least loaded
        return 1;
      default:
        return 0;  // Auto
    }
  }

 private:
  Strategy strategy_;
  uint32_t current_core_;
};

}  // namespace ai_inference
