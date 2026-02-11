#ifndef DATA_PROCESSING_MEMORY_POOL_HPP_
#define DATA_PROCESSING_MEMORY_POOL_HPP_

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <vector>

namespace data_processing {

/**
 * @brief Fixed-size memory pool for predictable, lock-free-friendly allocation.
 *
 * Pre-allocates a pool of fixed-size blocks to avoid dynamic allocation
 * during real-time processing. Thread-safe with mutex protection.
 */
class MemoryPool {
 public:
  /**
   * @param block_size Size of each block in bytes.
   * @param block_count Number of pre-allocated blocks.
   */
  MemoryPool(size_t block_size, size_t block_count);
  ~MemoryPool();

  MemoryPool(const MemoryPool&) = delete;
  MemoryPool& operator=(const MemoryPool&) = delete;

  /// Allocate a block from the pool. Returns nullptr if exhausted.
  void* Allocate();

  /// Return a block to the pool.
  void Free(void* ptr);

  /// Number of available blocks.
  size_t Available() const;

  /// Total number of blocks.
  size_t Capacity() const { return block_count_; }

  /// Size of each block.
  size_t BlockSize() const { return block_size_; }

 private:
  size_t block_size_;
  size_t block_count_;
  std::vector<uint8_t> storage_;
  std::vector<void*> free_list_;
  mutable std::mutex mutex_;
};

}  // namespace data_processing

#endif  // DATA_PROCESSING_MEMORY_POOL_HPP_
