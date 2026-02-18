#ifndef NEURO_HAL_DMABUF_SIM_HPP_
#define NEURO_HAL_DMABUF_SIM_HPP_

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace neuro::hal {

/**
 * @brief DMA-BUF sharing simulation for development without RK3588 hardware.
 *
 * Simulates the DMA-BUF fd-based zero-copy buffer sharing mechanism used
 * in the V4L2 → MPP → RGA → RKNN pipeline. On real hardware, these would
 * be kernel-allocated CMA buffers exported as file descriptors.
 *
 * This simulation uses heap memory with fake fd numbers, allowing the
 * pipeline logic to be developed and tested on Mac/x86.
 */
class DmaBufSim {
 public:
  struct BufferInfo {
    int fd;                ///< Simulated file descriptor
    void* virt_addr;       ///< Virtual address of the buffer
    uint64_t phys_addr;    ///< Simulated physical address
    size_t size;           ///< Buffer size in bytes
    bool exported;         ///< Whether this buffer has been exported
  };

  explicit DmaBufSim(uint64_t phys_base = 0x10000000);
  ~DmaBufSim();

  DmaBufSim(const DmaBufSim&) = delete;
  DmaBufSim& operator=(const DmaBufSim&) = delete;

  /// Allocate a DMA buffer and return its simulated fd.
  /// Returns -1 on failure.
  int Allocate(size_t size);

  /// Free a DMA buffer by fd.
  void Free(int fd);

  /// Export a buffer (mark as shared). Returns true on success.
  bool Export(int fd);

  /// Import a buffer by fd (simulates another process importing).
  /// Returns the virtual address, or nullptr if fd is invalid.
  void* Import(int fd);

  /// Get buffer info by fd. Returns nullptr if not found.
  const BufferInfo* GetBufferInfo(int fd) const;

  /// Map a buffer to get its virtual address.
  void* Mmap(int fd);

  /// Get total number of allocated buffers.
  size_t AllocatedCount() const;

  /// Get total allocated bytes.
  size_t AllocatedBytes() const;

 private:
  int NextFd();

  uint64_t phys_base_;
  uint64_t phys_next_;
  int next_fd_;
  mutable std::mutex mutex_;

  struct InternalBuffer {
    BufferInfo info;
    std::vector<uint8_t> storage;
  };
  std::unordered_map<int, std::unique_ptr<InternalBuffer>> buffers_;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_DMABUF_SIM_HPP_
