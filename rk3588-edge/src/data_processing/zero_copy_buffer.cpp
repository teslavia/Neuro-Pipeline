#include "common/buffer.hpp"

#include <cstring>
#include <vector>

namespace common {

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

// TODO: DMABuffer implementation (requires Linux DRM/DMA-BUF APIs)
// class DMABuffer : public Buffer { ... };

std::shared_ptr<Buffer> BufferFactory::CreateDMABuffer(size_t size) {
  // TODO: Implement DMA buffer allocation via DRM
  // For now, fallback to heap buffer
  return std::make_shared<HeapBuffer>(size);
}

std::shared_ptr<Buffer> BufferFactory::CreateMappedBuffer(void* data, size_t size) {
  return std::make_shared<HeapBuffer>(data, size);
}

}  // namespace common
