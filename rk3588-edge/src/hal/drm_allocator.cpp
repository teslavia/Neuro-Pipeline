#include "rk_hal/drm_allocator.hpp"

#include <cstring>
#include <iostream>
#include <vector>

#ifndef USE_MOCK_HAL

// ============================================================================
// Real DRM/DMA-BUF implementation (Linux/RK3588)
// ============================================================================
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

// DRM UAPI definitions (stable kernel ABI, avoids libdrm-dev dependency)
#include <linux/types.h>

#ifndef DRM_IOCTL_BASE
#define DRM_IOCTL_BASE 'd'
#define DRM_IO(nr)           _IO(DRM_IOCTL_BASE, nr)
#define DRM_IOWR(nr, type)   _IOWR(DRM_IOCTL_BASE, nr, type)

struct drm_mode_create_dumb {
  __u32 height;
  __u32 width;
  __u32 bpp;
  __u32 flags;
  __u32 handle;
  __u32 pitch;
  __u64 size;
};

struct drm_mode_map_dumb {
  __u32 handle;
  __u32 pad;
  __u64 offset;
};

struct drm_mode_destroy_dumb {
  __u32 handle;
};

struct drm_gem_close {
  __u32 handle;
  __u32 pad;
};

struct drm_prime_handle {
  __u32 handle;
  __u32 flags;
  __s32 fd;
};

#define DRM_IOCTL_MODE_CREATE_DUMB   DRM_IOWR(0xB2, struct drm_mode_create_dumb)
#define DRM_IOCTL_MODE_MAP_DUMB      DRM_IOWR(0xB3, struct drm_mode_map_dumb)
#define DRM_IOCTL_MODE_DESTROY_DUMB  DRM_IOWR(0xB4, struct drm_mode_destroy_dumb)
#define DRM_IOCTL_GEM_CLOSE          DRM_IOW(0x09, struct drm_gem_close)
#define DRM_IOCTL_PRIME_HANDLE_TO_FD DRM_IOWR(0x2D, struct drm_prime_handle)
#define DRM_IOCTL_PRIME_FD_TO_HANDLE DRM_IOWR(0x2E, struct drm_prime_handle)

#define DRM_IOW(nr, type)    _IOW(DRM_IOCTL_BASE, nr, type)
#define DRM_CLOEXEC          O_CLOEXEC
#define DRM_RDWR             O_RDWR
#endif

#include <linux/dma-buf.h>

namespace {

/// Buffer backed by a DRM dumb buffer with DMA-BUF export.
class DRMBuffer : public common::Buffer {
 public:
  DRMBuffer(int drm_fd, uint32_t handle, int dmabuf_fd,
            void* mapped, size_t size)
      : drm_fd_(drm_fd),
        handle_(handle),
        dmabuf_fd_(dmabuf_fd),
        mapped_(mapped),
        size_(size),
        metadata_{} {}

  ~DRMBuffer() override {
    if (mapped_ && mapped_ != MAP_FAILED) {
      munmap(mapped_, size_);
    }
    if (dmabuf_fd_ >= 0) {
      close(dmabuf_fd_);
    }
    if (handle_ > 0) {
      struct drm_gem_close close_args = {};
      close_args.handle = handle_;
      ioctl(drm_fd_, DRM_IOCTL_GEM_CLOSE, &close_args);
    }
  }

  void* Data() override { return mapped_; }
  size_t Size() const override { return size_; }
  int GetDMABufFd() const override { return dmabuf_fd_; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }

  void SyncForDevice(bool for_device) override {
    if (dmabuf_fd_ < 0) return;
    struct dma_buf_sync sync = {};
    sync.flags = for_device
        ? (DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE)
        : (DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
    ioctl(dmabuf_fd_, DMA_BUF_IOCTL_SYNC, &sync);
  }

 private:
  int drm_fd_;          // Borrowed — owned by DRMAllocator
  uint32_t handle_;
  int dmabuf_fd_;
  void* mapped_;
  size_t size_;
  Metadata metadata_;
};

}  // namespace

namespace rk_hal {

class DRMAllocator::Impl {
 public:
  Impl() : drm_fd_(-1) {}

  ~Impl() {
    if (drm_fd_ >= 0) {
      close(drm_fd_);
      drm_fd_ = -1;
    }
  }

  bool Initialize() {
    // Try render node first (doesn't require DRM master)
    const char* devices[] = {"/dev/dri/renderD128", "/dev/dri/card0", nullptr};
    for (int i = 0; devices[i]; ++i) {
      drm_fd_ = open(devices[i], O_RDWR | O_CLOEXEC);
      if (drm_fd_ >= 0) {
        std::cout << "[DRMAllocator] Opened " << devices[i] << std::endl;
        return true;
      }
    }
    std::cerr << "[DRMAllocator] Failed to open DRM device" << std::endl;
    return false;
  }

  std::shared_ptr<common::Buffer> Allocate(size_t size) {
    if (drm_fd_ < 0) return nullptr;

    // Create dumb buffer
    struct drm_mode_create_dumb create = {};
    create.width = static_cast<uint32_t>(size);
    create.height = 1;
    create.bpp = 8;
    if (ioctl(drm_fd_, DRM_IOCTL_MODE_CREATE_DUMB, &create) < 0) {
      std::cerr << "[DRMAllocator] CREATE_DUMB failed: " << strerror(errno) << std::endl;
      return nullptr;
    }

    // Export as DMA-BUF fd
    struct drm_prime_handle prime = {};
    prime.handle = create.handle;
    prime.flags = DRM_CLOEXEC | DRM_RDWR;
    if (ioctl(drm_fd_, DRM_IOCTL_PRIME_HANDLE_TO_FD, &prime) < 0) {
      std::cerr << "[DRMAllocator] PRIME_HANDLE_TO_FD failed: " << strerror(errno) << std::endl;
      DestroyDumb(create.handle);
      return nullptr;
    }

    // Map for CPU access
    struct drm_mode_map_dumb map = {};
    map.handle = create.handle;
    if (ioctl(drm_fd_, DRM_IOCTL_MODE_MAP_DUMB, &map) < 0) {
      std::cerr << "[DRMAllocator] MAP_DUMB failed: " << strerror(errno) << std::endl;
      close(prime.fd);
      DestroyDumb(create.handle);
      return nullptr;
    }

    void* mapped = mmap(nullptr, create.size, PROT_READ | PROT_WRITE,
                        MAP_SHARED, drm_fd_, map.offset);
    if (mapped == MAP_FAILED) {
      std::cerr << "[DRMAllocator] mmap failed: " << strerror(errno) << std::endl;
      close(prime.fd);
      DestroyDumb(create.handle);
      return nullptr;
    }

    return std::make_shared<DRMBuffer>(
        drm_fd_, create.handle, prime.fd, mapped, create.size);
  }

  std::shared_ptr<common::Buffer> Import(int dmabuf_fd, size_t size) {
    if (drm_fd_ < 0 || dmabuf_fd < 0) return nullptr;

    // Import DMA-BUF fd to get a GEM handle
    struct drm_prime_handle prime = {};
    prime.fd = dmabuf_fd;
    if (ioctl(drm_fd_, DRM_IOCTL_PRIME_FD_TO_HANDLE, &prime) < 0) {
      std::cerr << "[DRMAllocator] PRIME_FD_TO_HANDLE failed: " << strerror(errno) << std::endl;
      return nullptr;
    }

    // Map for CPU access
    struct drm_mode_map_dumb map = {};
    map.handle = prime.handle;
    if (ioctl(drm_fd_, DRM_IOCTL_MODE_MAP_DUMB, &map) < 0) {
      std::cerr << "[DRMAllocator] MAP_DUMB (import) failed: " << strerror(errno) << std::endl;
      return nullptr;
    }

    void* mapped = mmap(nullptr, size, PROT_READ | PROT_WRITE,
                        MAP_SHARED, drm_fd_, map.offset);
    if (mapped == MAP_FAILED) {
      std::cerr << "[DRMAllocator] mmap (import) failed: " << strerror(errno) << std::endl;
      return nullptr;
    }

    // Dup the fd so DRMBuffer owns its own copy
    int dup_fd = dup(dmabuf_fd);
    return std::make_shared<DRMBuffer>(drm_fd_, prime.handle, dup_fd, mapped, size);
  }

 private:
  void DestroyDumb(uint32_t handle) {
    struct drm_mode_destroy_dumb destroy = {};
    destroy.handle = handle;
    ioctl(drm_fd_, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy);
  }

  int drm_fd_;
};

#else  // USE_MOCK_HAL

// ============================================================================
// Mock implementation using DmaBufSim (Mac / x86 development)
// ============================================================================
#include "rk_hal/dmabuf_sim.hpp"

namespace {

/// Mock buffer backed by DmaBufSim heap allocation.
class MockDRMBuffer : public common::Buffer {
 public:
  MockDRMBuffer(rk_hal::DmaBufSim* sim, int fd, void* data, size_t size)
      : sim_(sim), fd_(fd), data_(data), size_(size), metadata_{} {}

  ~MockDRMBuffer() override {
    if (sim_ && fd_ >= 0) {
      sim_->Free(fd_);
    }
  }

  void* Data() override { return data_; }
  size_t Size() const override { return size_; }
  int GetDMABufFd() const override { return fd_; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }
  void SyncForDevice(bool /*for_device*/) override {}

 private:
  rk_hal::DmaBufSim* sim_;
  int fd_;
  void* data_;
  size_t size_;
  Metadata metadata_;
};

}  // namespace

namespace rk_hal {

class DRMAllocator::Impl {
 public:
  Impl() : sim_(std::make_unique<DmaBufSim>()) {}
  ~Impl() = default;

  bool Initialize() {
    std::cout << "[DRMAllocator] Mock mode initialized" << std::endl;
    return true;
  }

  std::shared_ptr<common::Buffer> Allocate(size_t size) {
    int fd = sim_->Allocate(size);
    if (fd < 0) return nullptr;
    void* data = sim_->Mmap(fd);
    if (!data) {
      sim_->Free(fd);
      return nullptr;
    }
    return std::make_shared<MockDRMBuffer>(sim_.get(), fd, data, size);
  }

  std::shared_ptr<common::Buffer> Import(int dmabuf_fd, size_t /*size*/) {
    void* data = sim_->Import(dmabuf_fd);
    if (!data) return nullptr;
    auto info = sim_->GetBufferInfo(dmabuf_fd);
    if (!info) return nullptr;
    // Don't free on import — the original owner manages lifetime
    return std::make_shared<MockDRMBuffer>(nullptr, dmabuf_fd, data, info->size);
  }

 private:
  std::unique_ptr<DmaBufSim> sim_;
};

#endif  // USE_MOCK_HAL

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
