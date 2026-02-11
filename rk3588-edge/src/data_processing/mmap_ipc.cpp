#include "common/mmap_ipc.hpp"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace data_processing {

MmapSharedMemory::MmapSharedMemory(const std::string& name, size_t size, Mode mode)
    : name_(name), size_(size), mode_(mode), data_(nullptr), fd_(-1),
      is_owner_(mode == Mode::kCreate) {
  int flags = O_RDWR;
  if (mode == Mode::kCreate) {
    flags |= O_CREAT | O_EXCL;
  }

  fd_ = shm_open(name_.c_str(), flags, 0666);
  if (fd_ < 0) {
    // If kCreate fails with EEXIST, try unlinking and recreating
    if (mode == Mode::kCreate && errno == EEXIST) {
      shm_unlink(name_.c_str());
      fd_ = shm_open(name_.c_str(), flags, 0666);
    }
    if (fd_ < 0) {
      throw std::runtime_error(
          "shm_open failed: " + name_ + " - " + std::strerror(errno));
    }
  }

  // Set size (only for creator)
  if (mode == Mode::kCreate) {
    if (ftruncate(fd_, static_cast<off_t>(size_)) < 0) {
      close(fd_);
      shm_unlink(name_.c_str());
      throw std::runtime_error(
          "ftruncate failed: " + std::string(std::strerror(errno)));
    }
  } else {
    // For consumer, get actual size from file
    struct stat st;
    if (fstat(fd_, &st) == 0) {
      size_ = static_cast<size_t>(st.st_size);
    }
  }

  // mmap the shared memory
  data_ = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
  if (data_ == MAP_FAILED) {
    data_ = nullptr;
    close(fd_);
    if (is_owner_) {
      shm_unlink(name_.c_str());
    }
    throw std::runtime_error(
        "mmap failed: " + std::string(std::strerror(errno)));
  }
}

MmapSharedMemory::~MmapSharedMemory() {
  Cleanup();
}

MmapSharedMemory::MmapSharedMemory(MmapSharedMemory&& other) noexcept
    : name_(std::move(other.name_)),
      size_(other.size_),
      mode_(other.mode_),
      data_(other.data_),
      fd_(other.fd_),
      is_owner_(other.is_owner_) {
  other.data_ = nullptr;
  other.fd_ = -1;
  other.is_owner_ = false;
}

MmapSharedMemory& MmapSharedMemory::operator=(MmapSharedMemory&& other) noexcept {
  if (this != &other) {
    Cleanup();
    name_ = std::move(other.name_);
    size_ = other.size_;
    mode_ = other.mode_;
    data_ = other.data_;
    fd_ = other.fd_;
    is_owner_ = other.is_owner_;
    other.data_ = nullptr;
    other.fd_ = -1;
    other.is_owner_ = false;
  }
  return *this;
}

size_t MmapSharedMemory::Write(const void* src, size_t len, size_t offset) {
  if (!data_ || !src) return 0;
  if (offset >= size_) return 0;

  size_t bytes_to_write = std::min(len, size_ - offset);
  std::memcpy(static_cast<uint8_t*>(data_) + offset, src, bytes_to_write);
  return bytes_to_write;
}

size_t MmapSharedMemory::Read(void* dst, size_t len, size_t offset) const {
  if (!data_ || !dst) return 0;
  if (offset >= size_) return 0;

  size_t bytes_to_read = std::min(len, size_ - offset);
  std::memcpy(dst, static_cast<const uint8_t*>(data_) + offset, bytes_to_read);
  return bytes_to_read;
}

void MmapSharedMemory::Unlink(const std::string& name) {
  shm_unlink(name.c_str());
}

void MmapSharedMemory::Cleanup() {
  if (data_ && data_ != MAP_FAILED) {
    munmap(data_, size_);
    data_ = nullptr;
  }
  if (fd_ >= 0) {
    close(fd_);
    fd_ = -1;
  }
  if (is_owner_ && !name_.empty()) {
    shm_unlink(name_.c_str());
    is_owner_ = false;
  }
}

}  // namespace data_processing
