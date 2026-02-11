#include "rk_hal/drm_allocator.hpp"

namespace rk_hal {

class DRMAllocator::Impl {
 public:
  Impl() : drm_fd_(-1) {}

  ~Impl() {
    if (drm_fd_ >= 0) {
      // TODO: close(drm_fd_);
    }
  }

  bool Initialize() {
    // TODO: Implement DRM allocator initialization
    // 1. drm_fd_ = open("/dev/dri/card0", O_RDWR | O_CLOEXEC)
    // 2. Verify DRM capabilities
    return false;
  }

  std::shared_ptr<common::Buffer> Allocate(size_t /*size*/) {
    // TODO: Allocate CMA-backed DMA buffer
    // 1. struct drm_mode_create_dumb create = {.height=1, .width=size, .bpp=8}
    // 2. ioctl(drm_fd_, DRM_IOCTL_MODE_CREATE_DUMB, &create)
    // 3. ioctl(drm_fd_, DRM_IOCTL_PRIME_HANDLE_TO_FD, ...) -> get dma_buf_fd
    // 4. mmap() for CPU access
    // 5. Wrap in Buffer
    return nullptr;
  }

  std::shared_ptr<common::Buffer> Import(int /*dmabuf_fd*/, size_t /*size*/) {
    // TODO: Import existing DMA-BUF fd
    // 1. ioctl(drm_fd_, DRM_IOCTL_PRIME_FD_TO_HANDLE, ...)
    // 2. mmap() for CPU access
    // 3. Wrap in Buffer
    return nullptr;
  }

 private:
  int drm_fd_;
};

DRMAllocator::DRMAllocator() : impl_(std::make_unique<Impl>()) {}
DRMAllocator::~DRMAllocator() = default;

bool DRMAllocator::Initialize() { return impl_->Initialize(); }

std::shared_ptr<common::Buffer> DRMAllocator::Allocate(size_t size) {
  return impl_->Allocate(size);
}

std::shared_ptr<common::Buffer> DRMAllocator::Import(int dmabuf_fd, size_t size) {
  return impl_->Import(dmabuf_fd, size);
}

}  // namespace rk_hal
