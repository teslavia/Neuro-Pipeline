#ifndef RK_HAL_DRM_ALLOCATOR_HPP_
#define RK_HAL_DRM_ALLOCATOR_HPP_

#include <cstddef>
#include <memory>

#include "common/buffer.hpp"

namespace rk_hal {

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
  std::shared_ptr<common::Buffer> Allocate(size_t size);

  /// Import an existing DMA-BUF fd as a Buffer object.
  std::shared_ptr<common::Buffer> Import(int dmabuf_fd, size_t size);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace rk_hal

#endif  // RK_HAL_DRM_ALLOCATOR_HPP_
