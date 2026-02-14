#ifndef DATA_PROCESSING_THREAD_POOL_HPP_
#define DATA_PROCESSING_THREAD_POOL_HPP_

#include <condition_variable>
#include <functional>
#include <future>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>

namespace data_processing {

/**
 * @brief Simple C++ thread pool using std::thread, std::mutex,
 *        std::condition_variable.
 *
 * Supports task submission with std::future result retrieval.
 */
class ThreadPool {
 public:
  explicit ThreadPool(size_t num_threads, size_t max_queue_size = 0);
  ~ThreadPool();

  ThreadPool(const ThreadPool&) = delete;
  ThreadPool& operator=(const ThreadPool&) = delete;

  /// Submit a task and get a future for the result.
  template <typename F, typename... Args>
  auto Submit(F&& f, Args&&... args)
      -> std::future<typename std::invoke_result_t<F, Args...>>;

  /// Number of worker threads.
  size_t Size() const { return workers_.size(); }

  /// Number of pending tasks in the queue.
  size_t PendingTasks() const;

  /// Shutdown the pool (waits for pending tasks).
  void Shutdown();

 private:
  std::vector<std::thread> workers_;
  std::queue<std::function<void()>> tasks_;
  mutable std::mutex mutex_;
  std::condition_variable cv_;
  bool stop_ = false;
  size_t max_queue_size_ = 0;  // 0 = unlimited
};

// Template implementation must be in header
template <typename F, typename... Args>
auto ThreadPool::Submit(F&& f, Args&&... args)
    -> std::future<typename std::invoke_result_t<F, Args...>> {
  using return_type = typename std::invoke_result_t<F, Args...>;

  auto task = std::make_shared<std::packaged_task<return_type()>>(
      std::bind(std::forward<F>(f), std::forward<Args>(args)...));

  std::future<return_type> result = task->get_future();

  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stop_) {
      throw std::runtime_error("Submit on stopped ThreadPool");
    }
    if (max_queue_size_ > 0 && tasks_.size() >= max_queue_size_) {
      throw std::runtime_error("ThreadPool queue full");
    }
    tasks_.emplace([task]() { (*task)(); });
  }

  cv_.notify_one();
  return result;
}

}  // namespace data_processing

#endif  // DATA_PROCESSING_THREAD_POOL_HPP_
