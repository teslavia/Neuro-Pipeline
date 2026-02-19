#include "neuro/core/buffer.hpp"
#include "neuro/hal/drm_allocator.hpp"

#include <cstring>
#include <memory>
#include <mutex>
#include <vector>

namespace neuro::core {

/// Heap-backed buffer implementation (for development/testing without DMA).
class HeapBuffer : public Buffer {
 public:
  HeapBuffer(size_t size) : data_(size), metadata_{} {}

  HeapBuffer(void* data, size_t size) : data_(size), metadata_{} {
    std::memcpy(data_.data(), data, size);
  }

  void* Data() override { return data_.data(); }
  size_t Size() const override { return data_.size(); }
  int GetDMABufFd() const override { return -1; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }
  void SyncForDevice(bool /*for_device*/) override {}

 private:
  std::vector<uint8_t> data_;
  Metadata metadata_;
};

/// Get or create the global DRM allocator instance (thread-safe lazy init).
static hal::DRMAllocator& GetGlobalDRMAllocator() {
  static std::mutex g_drm_mutex;
  static std::unique_ptr<hal::DRMAllocator> g_drm_allocator;
  static bool g_drm_initialized = false;

  std::lock_guard<std::mutex> lock(g_drm_mutex);
  if (!g_drm_initialized) {
    g_drm_allocator = std::make_unique<hal::DRMAllocator>();
    if (g_drm_allocator->Initialize()) {
      g_drm_initialized = true;
    } else {
      // Initialize failed - allocator will remain null
      g_drm_allocator.reset();
      g_drm_initialized = true;  // Mark as attempted to avoid retry
    }
  }

  // Return a reference - may be null if init failed
  static hal::DRMAllocator null_allocator;
  return g_drm_allocator ? *g_drm_allocator : null_allocator;
}

std::shared_ptr<Buffer> BufferFactory::CreateDMABuffer(size_t size) {
  // Try to allocate via DRM allocator for zero-copy
  auto& allocator = GetGlobalDRMAllocator();
  auto buffer = allocator.Allocate(size);
  if (buffer) {
    return buffer;
  }

  // Fallback to heap buffer if DRM allocation fails
  // (e.g., in development environments without DRM device)
  return std::make_shared<HeapBuffer>(size);
}

std::shared_ptr<Buffer> BufferFactory::CreateMappedBuffer(void* data, size_t size) {
  return std::make_shared<HeapBuffer>(data, size);
}

}  // namespace neuro::core
