#ifndef NEURO_HAL_DRM_ALLOCATOR_HPP_
#define NEURO_HAL_DRM_ALLOCATOR_HPP_

#include <cstddef>
#include <memory>

#include "neuro/core/buffer.hpp"

namespace neuro::hal {

/**
 * @brief DRM/DMA-BUF memory allocator.
 *
 * Allocates CMA-backed DMA buffers via DRM for zero-copy sharing
 * between V4L2, RGA, and NPU hardware units.
 */
class DRMAllocator {
 public:
  DRMAllocator();
  ~DRMAllocator();

  DRMAllocator(const DRMAllocator&) = delete;
  DRMAllocator& operator=(const DRMAllocator&) = delete;

  bool Initialize();

  /// Allocate a DMA buffer of given size.
  std::shared_ptr<core::Buffer> Allocate(size_t size);

  /// Import an existing DMA-BUF fd as a Buffer object.
  std::shared_ptr<core::Buffer> Import(int dmabuf_fd, size_t size);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_DRM_ALLOCATOR_HPP_
