#include "common/memory_pool.hpp"

#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace data_processing {

MemoryPool::MemoryPool(size_t block_size, size_t block_count)
    : block_size_(block_size),
      block_count_(block_count),
      storage_(block_size * block_count) {
  // Pre-populate free list
  free_list_.reserve(block_count);
  for (size_t i = 0; i < block_count; ++i) {
    free_list_.push_back(storage_.data() + i * block_size);
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
  return ptr;
}

void MemoryPool::Free(void* ptr) {
  if (!ptr) return;

  std::lock_guard<std::mutex> lock(mutex_);

  // Validate pointer is within our storage
  auto* byte_ptr = static_cast<uint8_t*>(ptr);
  if (byte_ptr < storage_.data() ||
      byte_ptr >= storage_.data() + storage_.size()) {
    throw std::invalid_argument("Pointer does not belong to this pool");
  }

  free_list_.push_back(ptr);
}

size_t MemoryPool::Available() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return free_list_.size();
}

}  // namespace data_processing
