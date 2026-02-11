#ifndef DATA_PROCESSING_VIRTUAL_DEVICE_IO_HPP_
#define DATA_PROCESSING_VIRTUAL_DEVICE_IO_HPP_

#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace data_processing {

/**
 * @brief Virtual device file I/O simulation.
 *
 * Simulates Linux device file operations (/dev/*, /sys/*, /proc/*)
 * for testing device driver interaction patterns without real hardware.
 * Models the open/read/write/ioctl pattern used by V4L2, DRM, and
 * other RK3588 subsystems.
 */
class VirtualDeviceIO {
 public:
  /// Simulated ioctl request handler.
  using IoctlHandler = std::function<int(unsigned long request, void* arg)>;

  VirtualDeviceIO();
  ~VirtualDeviceIO();

  /// Register a virtual device with initial content.
  /// @param path Device path (e.g., "/dev/video0")
  /// @param initial_content Initial readable content
  /// @return true if registered successfully
  bool RegisterDevice(const std::string& path,
                      const std::vector<uint8_t>& initial_content = {});

  /// Register an ioctl handler for a device.
  void RegisterIoctl(const std::string& path, unsigned long request,
                     IoctlHandler handler);

  /// Open a virtual device. Returns fd (>=0) or -1 on error.
  int Open(const std::string& path);

  /// Close a virtual device fd.
  int Close(int fd);

  /// Read from a virtual device.
  /// @return Number of bytes read, or -1 on error.
  ssize_t Read(int fd, void* buf, size_t count);

  /// Write to a virtual device.
  /// @return Number of bytes written, or -1 on error.
  ssize_t Write(int fd, const void* buf, size_t count);

  /// Perform ioctl on a virtual device.
  /// @return Handler result, or -1 if no handler registered.
  int Ioctl(int fd, unsigned long request, void* arg);

  /// Check if a device is registered.
  bool DeviceExists(const std::string& path) const;

  /// Check if an fd is open.
  bool IsOpen(int fd) const;

  /// Get the content of a device (for test verification).
  std::vector<uint8_t> GetDeviceContent(const std::string& path) const;

 private:
  struct Device {
    std::string path;
    std::vector<uint8_t> content;
    size_t read_offset = 0;
    std::unordered_map<unsigned long, IoctlHandler> ioctl_handlers;
  };

  int NextFd();
  Device* FindDeviceByFd(int fd);
  const Device* FindDeviceByFd(int fd) const;

  int next_fd_;
  mutable std::mutex mutex_;
  std::unordered_map<std::string, Device> devices_;
  std::unordered_map<int, std::string> open_fds_;  // fd → device path
};

}  // namespace data_processing

#endif  // DATA_PROCESSING_VIRTUAL_DEVICE_IO_HPP_
