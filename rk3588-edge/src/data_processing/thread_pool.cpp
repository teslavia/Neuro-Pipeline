#include "common/thread_pool.hpp"

namespace data_processing {

ThreadPool::ThreadPool(size_t num_threads, size_t max_queue_size)
    : max_queue_size_(max_queue_size) {
  for (size_t i = 0; i < num_threads; ++i) {
    workers_.emplace_back([this] {
      while (true) {
        std::function<void()> task;
        {
          std::unique_lock<std::mutex> lock(mutex_);
          cv_.wait(lock, [this] { return stop_ || !tasks_.empty(); });

          if (stop_ && tasks_.empty()) {
            return;
          }

          task = std::move(tasks_.front());
          tasks_.pop();
        }
        task();
      }
    });
  }
}

ThreadPool::~ThreadPool() {
  Shutdown();
}

void ThreadPool::Shutdown() {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stop_) return;
    stop_ = true;
  }
  cv_.notify_all();

  for (auto& worker : workers_) {
    if (worker.joinable()) {
      worker.join();
    }
  }
}

size_t ThreadPool::PendingTasks() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return tasks_.size();
}

}  // namespace data_processing
