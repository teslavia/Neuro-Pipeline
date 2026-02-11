#ifndef DATA_PROCESSING_MMAP_IPC_HPP_
#define DATA_PROCESSING_MMAP_IPC_HPP_

#include <cstddef>
#include <cstdint>
#include <string>

namespace data_processing {

/**
 * @brief POSIX shared memory wrapper using mmap for IPC.
 *
 * Provides RAII management of shared memory regions created via
 * shm_open + mmap. Supports both creator and consumer roles.
 */
class MmapSharedMemory {
 public:
  enum class Mode {
    kCreate,   // Create new shared memory (owner)
    kOpen,     // Open existing shared memory (consumer)
  };

  /**
   * @param name  Shared memory name (e.g., "/neuro_pipeline_shm").
   * @param size  Size in bytes (only used in kCreate mode).
   * @param mode  Create or Open.
   */
  MmapSharedMemory(const std::string& name, size_t size, Mode mode);
  ~MmapSharedMemory();

  MmapSharedMemory(const MmapSharedMemory&) = delete;
  MmapSharedMemory& operator=(const MmapSharedMemory&) = delete;
  MmapSharedMemory(MmapSharedMemory&& other) noexcept;
  MmapSharedMemory& operator=(MmapSharedMemory&& other) noexcept;

  /// Get pointer to mapped memory region.
  void* Data() { return data_; }
  const void* Data() const { return data_; }

  /// Get mapped region size.
  size_t Size() const { return size_; }

  /// Check if mapping is valid.
  bool IsValid() const { return data_ != nullptr; }

  /// Get shared memory name.
  const std::string& Name() const { return name_; }

  /// Write data at offset. Returns bytes written.
  size_t Write(const void* src, size_t len, size_t offset = 0);

  /// Read data at offset. Returns bytes read.
  size_t Read(void* dst, size_t len, size_t offset = 0) const;

  /// Unlink the shared memory object (only owner should call this).
  static void Unlink(const std::string& name);

 private:
  std::string name_;
  size_t size_;
  Mode mode_;
  void* data_;
  int fd_;
  bool is_owner_;

  void Cleanup();
};

}  // namespace data_processing

#endif  // DATA_PROCESSING_MMAP_IPC_HPP_
