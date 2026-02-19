#ifndef NEURO_COMM_DETECTION_QUEUE_HPP_
#define NEURO_COMM_DETECTION_QUEUE_HPP_

#include <atomic>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>

namespace neuro_pipeline {
class DetectionResult;
}

namespace neuro::comm {

/// Bounded ring queue for buffering detection results during gRPC disconnects.
/// Thread-safe. When full, evicts oldest entries (FIFO).
class DetectionQueue {
 public:
  struct Config {
    size_t max_entries = 1000;                    // ~33s @30fps
    size_t max_memory_bytes = 64 * 1024 * 1024;  // 64MB
  };

  DetectionQueue();
  explicit DetectionQueue(const Config& config);

  /// Enqueue a detection result. Evicts oldest if at capacity. Returns true.
  bool Enqueue(const neuro_pipeline::DetectionResult& result);

  /// Dequeue oldest entry into |result|. Returns false if empty.
  bool Dequeue(neuro_pipeline::DetectionResult* result);

  size_t Size() const;
  bool Empty() const;

  uint64_t EnqueuedTotal() const { return enqueued_.load(std::memory_order_relaxed); }
  uint64_t DroppedTotal() const { return dropped_.load(std::memory_order_relaxed); }

 private:
  void EvictOldest();

  Config config_;
  std::deque<std::string> queue_;  // serialized protobuf bytes
  size_t current_bytes_ = 0;
  mutable std::mutex mu_;
  std::atomic<uint64_t> enqueued_{0};
  std::atomic<uint64_t> dropped_{0};
};

}  // namespace neuro::comm

#endif  // NEURO_COMM_DETECTION_QUEUE_HPP_
