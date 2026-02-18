#include "neuro/core/memory_pool.hpp"

#include <cstring>
#include <stdexcept>

namespace neuro::core {

MemoryPool::MemoryPool(size_t block_size, size_t block_count,
                       uint64_t phys_base_addr, size_t alignment)
    : block_size_(block_size),
      block_count_(block_count),
      phys_base_addr_(phys_base_addr),
      alignment_(alignment),
      storage_(block_size * block_count + (alignment > 0 ? alignment : 0)) {
  // Pre-populate free list with properly aligned pointers
  free_list_.reserve(block_count);
  for (size_t i = 0; i < block_count; ++i) {
    uint8_t* ptr = storage_.data() + i * block_size;
    if (alignment_ > 0) {
      auto addr = reinterpret_cast<uintptr_t>(ptr);
      auto aligned = (addr + alignment_ - 1) & ~(alignment_ - 1);
      // Only align the first block; subsequent blocks are block_size apart
      // which works if block_size is a multiple of alignment
      if (i == 0 && aligned != addr) {
        ptr = reinterpret_cast<uint8_t*>(aligned);
      }
    }
    free_list_.push_back(ptr);
  }
}

MemoryPool::~MemoryPool() = default;

void* MemoryPool::Allocate() {
  std::lock_guard<std::mutex> lock(mutex_);
  if (free_list_.empty()) {
    return nullptr;
  }
  void* ptr = free_list_.back();
  free_list_.pop_back();
  stats_.total_allocations++;
  size_t in_use = block_count_ - free_list_.size();
  if (in_use > stats_.peak_usage) stats_.peak_usage = in_use;
  return ptr;
}

void MemoryPool::Free(void* ptr) {
  if (!ptr) return;

  std::lock_guard<std::mutex> lock(mutex_);

  auto* byte_ptr = static_cast<uint8_t*>(ptr);
  if (byte_ptr < storage_.data() ||
      byte_ptr >= storage_.data() + storage_.size()) {
    throw std::invalid_argument("Pointer does not belong to this pool");
  }

  free_list_.push_back(ptr);
  stats_.total_frees++;
}

size_t MemoryPool::Available() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return free_list_.size();
}

// ---- Physical / Virtual Address Simulation ----

bool MemoryPool::ContainsVirt(const void* virt_addr) const {
  auto* byte_ptr = static_cast<const uint8_t*>(virt_addr);
  return byte_ptr >= storage_.data() &&
         byte_ptr < storage_.data() + storage_.size();
}

bool MemoryPool::ContainsPhys(uint64_t phys_addr) const {
  return phys_addr >= phys_base_addr_ && phys_addr < PhysEndAddr();
}

uint64_t MemoryPool::VirtToPhys(const void* virt_addr) const {
  if (!ContainsVirt(virt_addr)) return 0;

  auto offset = static_cast<size_t>(
      static_cast<const uint8_t*>(virt_addr) - storage_.data());
  return phys_base_addr_ + offset;
}

void* MemoryPool::PhysToVirt(uint64_t phys_addr) const {
  if (!ContainsPhys(phys_addr)) return nullptr;

  auto offset = static_cast<size_t>(phys_addr - phys_base_addr_);
  // const_cast is safe here: storage_ is mutable, but method is const
  // because it doesn't modify pool state (free_list_, mutex_)
  return const_cast<uint8_t*>(storage_.data()) + offset;
}

MemoryPool::Stats MemoryPool::GetStats() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return stats_;
}

}  // namespace data_processing
