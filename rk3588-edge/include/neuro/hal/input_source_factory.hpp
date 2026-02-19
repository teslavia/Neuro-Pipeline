#ifndef NEURO_HAL_INPUT_SOURCE_FACTORY_HPP_
#define NEURO_HAL_INPUT_SOURCE_FACTORY_HPP_

#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "neuro/hal/input_source.hpp"
#include "neuro/hal/mpp_decoder.hpp"
#include "neuro/hal/rtsp_source.hpp"
#include "neuro/hal/v4l2_camera.hpp"
#include "neuro/core/logger.hpp"

namespace neuro::hal {

// ── Concrete adapters ────────────────────────────────────

/// Wraps V4L2Camera behind InputSource.
class V4L2InputSource final : public InputSource {
 public:
  explicit V4L2InputSource(V4L2Camera::Config cfg)
      : cfg_(std::move(cfg)),
        cam_(std::make_unique<V4L2Camera>(cfg_)) {}

  bool Initialize() override { return cam_->Initialize(); }
  bool Start() override      { return cam_->Start(); }
  void Stop() override       { cam_->Stop(); }

  std::shared_ptr<core::Buffer> CaptureFrame() override {
    return cam_->CaptureFrame();
  }
  void ReleaseFrame(std::shared_ptr<core::Buffer> f) override {
    cam_->ReleaseFrame(std::move(f));
  }

  uint32_t Width() const override  { return cfg_.width; }
  uint32_t Height() const override { return cfg_.height; }

 private:
  V4L2Camera::Config cfg_;
  std::unique_ptr<V4L2Camera> cam_;
};

/// Wraps RTSPSource behind InputSource.
class RTSPInputSource final : public InputSource {
 public:
  explicit RTSPInputSource(RTSPSource::Config cfg)
      : cfg_(std::move(cfg)),
        src_(std::make_unique<RTSPSource>(cfg_)) {}

  bool Initialize() override { return src_->Initialize(); }
  bool Start() override      { return src_->Start(); }
  void Stop() override       { src_->Stop(); }

  std::shared_ptr<core::Buffer> CaptureFrame() override {
    return src_->CaptureFrame();
  }
  void ReleaseFrame(std::shared_ptr<core::Buffer> f) override {
    src_->ReleaseFrame(std::move(f));
  }

  uint32_t Width() const override  { return cfg_.width; }
  uint32_t Height() const override { return cfg_.height; }

 private:
  RTSPSource::Config cfg_;
  std::unique_ptr<RTSPSource> src_;
};

/// Wraps MPPDecoder + file I/O behind InputSource.
class VideoFileInputSource final : public InputSource {
 public:
  VideoFileInputSource(MPPDecoder::Config dec_cfg, std::string path)
      : dec_cfg_(dec_cfg), path_(std::move(path)) {}

  bool Initialize() override {
    decoder_ = std::make_unique<MPPDecoder>(dec_cfg_);
    if (!decoder_->Initialize()) return false;
    file_.open(path_, std::ios::binary);
    return file_.is_open();
  }

  bool Start() override { return true; }  // no-op for files
  void Stop() override  { file_.close(); }

  std::shared_ptr<core::Buffer> CaptureFrame() override {
    constexpr size_t kChunk = 64 * 1024;
    std::vector<uint8_t> buf(kChunk);
    file_.read(reinterpret_cast<char*>(buf.data()), kChunk);
    auto n = file_.gcount();
    if (n <= 0) return nullptr;
    return decoder_->Decode(buf.data(), static_cast<size_t>(n));
  }

  void ReleaseFrame(std::shared_ptr<core::Buffer>) override {}  // no pool

  uint32_t Width() const override  { return dec_cfg_.width; }
  uint32_t Height() const override { return dec_cfg_.height; }

 private:
  MPPDecoder::Config dec_cfg_;
  std::string path_;
  std::unique_ptr<MPPDecoder> decoder_;
  std::ifstream file_;
};

// ── Factory ──────────────────────────────────────────────

/// Builds the right InputSource from PipelineCoordinator::Config fields.
struct InputSourceFactory {
  /// Create a single InputSource from config.
  /// For multi-camera, call CreateMultiCamera() instead.
  static std::unique_ptr<InputSource> Create(
      const std::string& video_source,
      const std::string& camera_device,
      uint32_t width, uint32_t height, uint32_t fps) {
    // RTSP
    if (!video_source.empty() &&
        video_source.substr(0, 7) == "rtsp://") {
      RTSPSource::Config cfg;
      cfg.url = video_source;
      cfg.width = width;
      cfg.height = height;
      cfg.fps = fps;
      LOG_INFO("InputSourceFactory", "Creating RTSP source: %s",
               video_source.c_str());
      return std::make_unique<RTSPInputSource>(cfg);
    }

    // Camera
    if (video_source.empty()) {
      V4L2Camera::Config cfg;
      cfg.device_path = camera_device;
      cfg.width = width;
      cfg.height = height;
      cfg.fps = fps;
      LOG_INFO("InputSourceFactory", "Creating V4L2 camera: %s",
               camera_device.c_str());
      return std::make_unique<V4L2InputSource>(cfg);
    }

    // Video file
    MPPDecoder::Config dec;
    dec.width = width;
    dec.height = height;
    dec.codec = 7;  // H.264
    LOG_INFO("InputSourceFactory", "Creating video file source: %s",
             video_source.c_str());
    return std::make_unique<VideoFileInputSource>(dec, video_source);
  }
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_INPUT_SOURCE_FACTORY_HPP_
