#ifndef RK_HAL_V4L2_CAMERA_HPP_
#define RK_HAL_V4L2_CAMERA_HPP_

#include <cstdint>
#include <memory>
#include <string>

#include "common/buffer.hpp"

namespace rk_hal {

/**
 * @brief V4L2 camera capture wrapper with zero-copy support.
 *
 * RAII management of V4L2 video capture device with MMAP or DMABUF
 * memory modes for zero-copy integration with RGA/NPU.
 */
class V4L2Camera {
 public:
  struct Config {
    std::string device_path = "/dev/video0";
    uint32_t width = 1920;
    uint32_t height = 1080;
    uint32_t fps = 30;
    uint32_t buffer_count = 4;
    bool use_dmabuf = true;
  };

  explicit V4L2Camera(const Config& config);
  ~V4L2Camera();

  V4L2Camera(const V4L2Camera&) = delete;
  V4L2Camera& operator=(const V4L2Camera&) = delete;
  V4L2Camera(V4L2Camera&&) noexcept;
  V4L2Camera& operator=(V4L2Camera&&) noexcept;

  bool Initialize();
  bool Start();
  std::shared_ptr<common::Buffer> CaptureFrame();
  void ReleaseFrame(std::shared_ptr<common::Buffer> buffer);
  void Stop();
  uint32_t GetFPS() const { return config_.fps; }

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  Config config_;
};

}  // namespace rk_hal

#endif  // RK_HAL_V4L2_CAMERA_HPP_
