#ifndef NEURO_HAL_RTSP_SOURCE_HPP_
#define NEURO_HAL_RTSP_SOURCE_HPP_

#include <memory>
#include <string>

#include "neuro/core/buffer.hpp"

namespace neuro::hal {

/**
 * @brief RTSP video source using FFmpeg libavformat.
 *
 * Provides the same interface as V4L2Camera for seamless integration
 * into the pipeline coordinator. Detects RTSP URLs by prefix.
 */
class RTSPSource {
 public:
  struct Config {
    std::string url;           // rtsp://host:port/stream
    uint32_t width = 1920;
    uint32_t height = 1080;
    uint32_t fps = 30;
    int timeout_ms = 5000;     // Connection timeout
    std::string transport = "tcp";  // "tcp" or "udp"
  };

  explicit RTSPSource(const Config& config);
  ~RTSPSource();

  RTSPSource(const RTSPSource&) = delete;
  RTSPSource& operator=(const RTSPSource&) = delete;

  bool Initialize();
  bool Start();
  void Stop();

  std::shared_ptr<core::Buffer> CaptureFrame();
  void ReleaseFrame(std::shared_ptr<core::Buffer> frame);

  bool IsOpen() const { return is_open_; }
  uint32_t Width() const { return config_.width; }
  uint32_t Height() const { return config_.height; }

 private:
  Config config_;
  bool is_open_ = false;

  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_RTSP_SOURCE_HPP_
