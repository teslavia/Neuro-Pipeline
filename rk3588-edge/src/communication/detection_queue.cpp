#include "neuro/comm/detection_queue.hpp"
#include "neuro/core/logger.hpp"
#include "neuro_pipeline.pb.h"

namespace neuro::comm {

DetectionQueue::DetectionQueue() : config_() {}
DetectionQueue::DetectionQueue(const Config& config) : config_(config) {}

bool DetectionQueue::Enqueue(const neuro_pipeline::DetectionResult& result) {
  std::string serialized;
  if (!result.SerializeToString(&serialized)) {
    LOG_ERROR("DetectionQueue", "Failed to serialize detection result");
    return false;
  }

  std::lock_guard<std::mutex> lock(mu_);

  // Evict oldest entries until we have room
  while (queue_.size() >= config_.max_entries ||
         (current_bytes_ + serialized.size() > config_.max_memory_bytes &&
          !queue_.empty())) {
    EvictOldest();
  }

  queue_.push_back(std::move(serialized));
  current_bytes_ += queue_.back().size();
  enqueued_.fetch_add(1, std::memory_order_relaxed);
  return true;
}

bool DetectionQueue::Dequeue(neuro_pipeline::DetectionResult* result) {
  std::lock_guard<std::mutex> lock(mu_);
  if (queue_.empty()) return false;

  const std::string& front = queue_.front();
  if (!result->ParseFromString(front)) {
    LOG_ERROR("DetectionQueue", "Failed to parse queued detection");
    current_bytes_ -= front.size();
    queue_.pop_front();
    return false;
  }

  current_bytes_ -= front.size();
  queue_.pop_front();
  return true;
}

size_t DetectionQueue::Size() const {
  std::lock_guard<std::mutex> lock(mu_);
  return queue_.size();
}

bool DetectionQueue::Empty() const {
  std::lock_guard<std::mutex> lock(mu_);
  return queue_.empty();
}

void DetectionQueue::EvictOldest() {
  // mu_ must be held by caller
  if (queue_.empty()) return;
  current_bytes_ -= queue_.front().size();
  queue_.pop_front();
  dropped_.fetch_add(1, std::memory_order_relaxed);
}

}  // namespace neuro::comm
