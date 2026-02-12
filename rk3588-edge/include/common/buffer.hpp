#ifndef COMMON_BUFFER_HPP_
#define COMMON_BUFFER_HPP_

#include <cstddef>
#include <cstdint>
#include <memory>

namespace common {

/**
 * @brief Unified buffer abstraction for zero-copy data flow.
 *
 * Represents a memory buffer shared between V4L2, RGA, and NPU
 * using DMA-BUF file descriptors. Supports both virtual address access
 * (CPU) and DMA-BUF sharing (hardware accelerators).
 */
class Buffer {
 public:
  struct Metadata {
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t stride = 0;       // Bytes per row
    uint32_t format = 0;       // FourCC format code
    uint64_t timestamp_us = 0;
    uint64_t frame_id = 0;
  };

  virtual ~Buffer() = default;

  /// Get virtual address for CPU access.
  virtual void* Data() = 0;

  /// Get buffer size in bytes.
  virtual size_t Size() const = 0;

  /// Get DMA-BUF file descriptor. Returns >= 0 if DMABUF, -1 otherwise.
  virtual int GetDMABufFd() const = 0;

  /// Get buffer metadata.
  virtual const Metadata& GetMetadata() const = 0;

  /// Set buffer metadata (dimensions, format, timestamp).
  virtual void SetMetadata(const Metadata& meta) = 0;

  /// Synchronize CPU cache.
  /// @param for_device true = flush (CPU→DMA), false = invalidate (DMA→CPU).
  virtual void SyncForDevice(bool for_device) = 0;
};

/**
 * @brief Factory for creating different buffer types.
 */
class BufferFactory {
 public:
  static std::shared_ptr<Buffer> CreateDMABuffer(size_t size);
  static std::shared_ptr<Buffer> CreateMappedBuffer(void* data, size_t size);
};

}  // namespace common

#endif  // COMMON_BUFFER_HPP_
