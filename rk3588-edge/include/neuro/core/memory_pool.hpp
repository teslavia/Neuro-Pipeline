#ifndef NEURO_CORE_MEMORY_POOL_HPP_
#define NEURO_CORE_MEMORY_POOL_HPP_

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>

namespace neuro::core {

/**
 * @brief Fixed-size memory pool with physical/virtual address simulation.
 *
 * Pre-allocates a pool of fixed-size blocks to avoid dynamic allocation
 * during real-time processing. Thread-safe with mutex protection.
 *
 * Simulates the physical/virtual address mapping found in DMA-BUF
 * zero-copy pipelines on RK3588. Virtual addresses are the actual
 * process-space pointers; physical addresses are simulated offsets
 * from a configurable base address (mimicking CMA region).
 */
class MemoryPool {
 public:
  struct Stats {
    size_t total_allocations = 0;
    size_t total_frees = 0;
    size_t peak_usage = 0;  // max blocks in use at once
  };

  /**
   * @param block_size Size of each block in bytes.
   * @param block_count Number of pre-allocated blocks.
   * @param phys_base_addr Simulated physical base address (default 0x10000000).
   * @param alignment Memory alignment in bytes (0 = no special alignment).
   */
  MemoryPool(size_t block_size, size_t block_count,
             uint64_t phys_base_addr = 0x10000000,
             size_t alignment = 0);
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

  // ---- Physical / Virtual Address Simulation ----

  /// Convert virtual address (process pointer) to simulated physical address.
  /// Returns 0 if the pointer does not belong to this pool.
  uint64_t VirtToPhys(const void* virt_addr) const;

  /// Convert simulated physical address to virtual address.
  /// Returns nullptr if the address is outside the pool's physical range.
  void* PhysToVirt(uint64_t phys_addr) const;

  /// Get the simulated physical base address of the pool.
  uint64_t PhysBaseAddr() const { return phys_base_addr_; }

  /// Get the total physical address range [base, base + total_size).
  uint64_t PhysEndAddr() const {
    return phys_base_addr_ + block_size_ * block_count_;
  }

  /// Check if a virtual address belongs to this pool.
  bool ContainsVirt(const void* virt_addr) const;

  /// Check if a physical address belongs to this pool.
  bool ContainsPhys(uint64_t phys_addr) const;

  /// Get allocation statistics.
  Stats GetStats() const;

  /// Get alignment setting.
  size_t Alignment() const { return alignment_; }

 private:
  size_t block_size_;
  size_t block_count_;
  uint64_t phys_base_addr_;
  size_t alignment_;
  std::vector<uint8_t> storage_;
  std::vector<void*> free_list_;
  mutable std::mutex mutex_;
  Stats stats_;
};

}  // namespace neuro::core

#endif  // NEURO_CORE_MEMORY_POOL_HPP_
