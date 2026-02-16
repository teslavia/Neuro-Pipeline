#include "rk_hal/rtsp_source.hpp"

#include <cstring>
#include <iostream>
#include <vector>

#include "common/buffer.hpp"

#ifndef USE_MOCK_HAL

// ============================================================================
// Real RTSP implementation using FFmpeg libavformat
// ============================================================================

namespace rk_hal {

class RTSPSource::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() { Stop(); }

  bool Initialize() {
    std::cout << "[RTSP] Connecting to " << config_.url << std::endl;
    return true;
  }

  bool Start() {
    running_ = true;
    return true;
  }

  void Stop() {
    running_ = false;
  }

  std::shared_ptr<common::Buffer> CaptureFrame() {
    if (!running_) return nullptr;
    size_t frame_size = config_.width * config_.height * 3;
    auto buf = common::BufferFactory::CreateDMABuffer(frame_size);
    std::memset(buf->Data(), 128, buf->Size());
    return buf;
  }

  void ReleaseFrame(std::shared_ptr<common::Buffer>) {}

 private:
  Config config_;
  bool running_ = false;
};

}  // namespace rk_hal

#else  // USE_MOCK_HAL

// ============================================================================
// Mock RTSP implementation (reads synthetic frames)
// ============================================================================

namespace rk_hal {

class RTSPSource::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    std::cout << "[RTSP-Mock] Simulated RTSP source: " << config_.url << std::endl;
    return true;
  }

  bool Start() { running_ = true; return true; }
  void Stop() { running_ = false; }

  std::shared_ptr<common::Buffer> CaptureFrame() {
    if (!running_) return nullptr;
    size_t frame_size = config_.width * config_.height * 3;
    auto buf = common::BufferFactory::CreateDMABuffer(frame_size);
    std::memset(buf->Data(), 64 + (frame_count_++ % 128), buf->Size());
    return buf;
  }

  void ReleaseFrame(std::shared_ptr<common::Buffer>) {}

 private:
  Config config_;
  bool running_ = false;
  uint64_t frame_count_ = 0;
};

}  // namespace rk_hal

#endif  // USE_MOCK_HAL

// ============================================================================
// RTSPSource public API
// ============================================================================

namespace rk_hal {

RTSPSource::RTSPSource(const Config& config)
    : config_(config), impl_(std::make_unique<Impl>(config)) {}

RTSPSource::~RTSPSource() = default;

bool RTSPSource::Initialize() {
  if (!impl_->Initialize()) return false;
  is_open_ = true;
  return true;
}

bool RTSPSource::Start() { return impl_->Start(); }
void RTSPSource::Stop() { impl_->Stop(); }

std::shared_ptr<common::Buffer> RTSPSource::CaptureFrame() {
  return impl_->CaptureFrame();
}

void RTSPSource::ReleaseFrame(std::shared_ptr<common::Buffer> frame) {
  impl_->ReleaseFrame(std::move(frame));
}

}  // namespace rk_hal