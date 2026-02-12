#include "rk_hal/dmabuf_sim.hpp"

namespace rk_hal {

DmaBufSim::DmaBufSim(uint64_t phys_base)
    : phys_base_(phys_base), phys_next_(phys_base), next_fd_(100) {}

DmaBufSim::~DmaBufSim() = default;

int DmaBufSim::NextFd() { return next_fd_++; }

int DmaBufSim::Allocate(size_t size) {
  if (size == 0) return -1;

  std::lock_guard<std::mutex> lock(mutex_);

  int fd = NextFd();
  auto buf = std::make_unique<InternalBuffer>();
  buf->storage.resize(size, 0);
  buf->info.fd = fd;
  buf->info.virt_addr = buf->storage.data();
  buf->info.phys_addr = phys_next_;
  buf->info.size = size;
  buf->info.exported = false;

  phys_next_ += size;
  // Align to page boundary
  phys_next_ = (phys_next_ + 4095) & ~static_cast<uint64_t>(4095);

  buffers_[fd] = std::move(buf);
  return fd;
}

void DmaBufSim::Free(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  buffers_.erase(fd);
}

bool DmaBufSim::Export(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = buffers_.find(fd);
  if (it == buffers_.end()) return false;
  it->second->info.exported = true;
  return true;
}

void* DmaBufSim::Import(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = buffers_.find(fd);
  if (it == buffers_.end()) return nullptr;
  if (!it->second->info.exported) return nullptr;
  return it->second->info.virt_addr;
}

const DmaBufSim::BufferInfo* DmaBufSim::GetBufferInfo(int fd) const {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = buffers_.find(fd);
  if (it == buffers_.end()) return nullptr;
  return &it->second->info;
}

void* DmaBufSim::Mmap(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = buffers_.find(fd);
  if (it == buffers_.end()) return nullptr;
  return it->second->info.virt_addr;
}

size_t DmaBufSim::AllocatedCount() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return buffers_.size();
}

size_t DmaBufSim::AllocatedBytes() const {
  std::lock_guard<std::mutex> lock(mutex_);
  size_t total = 0;
  for (const auto& pair : buffers_) {
    total += pair.second->info.size;
  }
  return total;
}

}  // namespace rk_hal
