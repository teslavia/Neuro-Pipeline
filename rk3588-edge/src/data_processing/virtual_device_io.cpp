#include "neuro/pipeline/virtual_device_io.hpp"

#include <algorithm>
#include <cstring>

namespace neuro::pipeline {

VirtualDeviceIO::VirtualDeviceIO() : next_fd_(10) {}

VirtualDeviceIO::~VirtualDeviceIO() = default;

int VirtualDeviceIO::NextFd() { return next_fd_++; }

VirtualDeviceIO::Device* VirtualDeviceIO::FindDeviceByFd(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto fd_it = open_fds_.find(fd);
  if (fd_it == open_fds_.end()) return nullptr;
  auto dev_it = devices_.find(fd_it->second);
  if (dev_it == devices_.end()) return nullptr;
  return &dev_it->second;
}

const VirtualDeviceIO::Device* VirtualDeviceIO::FindDeviceByFd(int fd) const {
  std::lock_guard<std::mutex> lock(mutex_);
  auto fd_it = open_fds_.find(fd);
  if (fd_it == open_fds_.end()) return nullptr;
  auto dev_it = devices_.find(fd_it->second);
  if (dev_it == devices_.end()) return nullptr;
  return &dev_it->second;
}

bool VirtualDeviceIO::RegisterDevice(
    const std::string& path, const std::vector<uint8_t>& initial_content) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (devices_.count(path)) return false;

  Device dev;
  dev.path = path;
  dev.content = initial_content;
  dev.read_offset = 0;
  devices_[path] = std::move(dev);
  return true;
}

void VirtualDeviceIO::RegisterIoctl(const std::string& path,
                                     unsigned long request,
                                     IoctlHandler handler) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = devices_.find(path);
  if (it != devices_.end()) {
    it->second.ioctl_handlers[request] = std::move(handler);
  }
}

int VirtualDeviceIO::Open(const std::string& path) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = devices_.find(path);
  if (it == devices_.end()) return -1;

  int fd = NextFd();
  open_fds_[fd] = path;
  // Reset read offset on open
  it->second.read_offset = 0;
  return fd;
}

int VirtualDeviceIO::Close(int fd) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = open_fds_.find(fd);
  if (it == open_fds_.end()) return -1;
  open_fds_.erase(it);
  return 0;
}

ssize_t VirtualDeviceIO::Read(int fd, void* buf, size_t count) {
  if (!buf) return -1;

  // FindDeviceByFd acquires lock internally, but we need atomic access
  // to both open_fds_ and devices_, so handle manually
  std::lock_guard<std::mutex> lock(mutex_);
  auto fd_it = open_fds_.find(fd);
  if (fd_it == open_fds_.end()) return -1;

  auto dev_it = devices_.find(fd_it->second);
  if (dev_it == devices_.end()) return -1;

  Device& dev = dev_it->second;
  if (dev.read_offset >= dev.content.size()) return 0;

  size_t available = dev.content.size() - dev.read_offset;
  size_t to_read = std::min(count, available);
  std::memcpy(buf, dev.content.data() + dev.read_offset, to_read);
  dev.read_offset += to_read;

  return static_cast<ssize_t>(to_read);
}

ssize_t VirtualDeviceIO::Write(int fd, const void* buf, size_t count) {
  if (!buf) return -1;

  std::lock_guard<std::mutex> lock(mutex_);
  auto fd_it = open_fds_.find(fd);
  if (fd_it == open_fds_.end()) return -1;

  auto dev_it = devices_.find(fd_it->second);
  if (dev_it == devices_.end()) return -1;

  Device& dev = dev_it->second;
  const auto* data = static_cast<const uint8_t*>(buf);
  dev.content.insert(dev.content.end(), data, data + count);

  return static_cast<ssize_t>(count);
}

int VirtualDeviceIO::Ioctl(int fd, unsigned long request, void* arg) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto fd_it = open_fds_.find(fd);
  if (fd_it == open_fds_.end()) return -1;

  auto dev_it = devices_.find(fd_it->second);
  if (dev_it == devices_.end()) return -1;

  auto handler_it = dev_it->second.ioctl_handlers.find(request);
  if (handler_it == dev_it->second.ioctl_handlers.end()) return -1;

  return handler_it->second(request, arg);
}

bool VirtualDeviceIO::DeviceExists(const std::string& path) const {
  std::lock_guard<std::mutex> lock(mutex_);
  return devices_.count(path) > 0;
}

bool VirtualDeviceIO::IsOpen(int fd) const {
  std::lock_guard<std::mutex> lock(mutex_);
  return open_fds_.count(fd) > 0;
}

std::vector<uint8_t> VirtualDeviceIO::GetDeviceContent(
    const std::string& path) const {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = devices_.find(path);
  if (it == devices_.end()) return {};
  return it->second.content;
}

}  // namespace data_processing
