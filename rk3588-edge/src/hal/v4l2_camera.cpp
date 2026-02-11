#include "rk_hal/v4l2_camera.hpp"

#include <stdexcept>

namespace rk_hal {

class V4L2Camera::Impl {
 public:
  explicit Impl(const Config& config) : config_(config), fd_(-1) {}

  ~Impl() {
    if (fd_ >= 0) {
      Stop();
      // TODO: close(fd_);
    }
  }

  bool Initialize() {
    // TODO: Implement V4L2 device initialization
    // 1. Open device: fd_ = open(config_.device_path.c_str(), O_RDWR | O_NONBLOCK)
    // 2. Query capabilities: VIDIOC_QUERYCAP
    // 3. Set format: VIDIOC_S_FMT (NV12, config_.width x config_.height)
    // 4. Set frame rate: VIDIOC_S_PARM
    // 5. Request buffers: VIDIOC_REQBUFS (MMAP or DMABUF mode)
    // 6. Query and mmap buffers: VIDIOC_QUERYBUF + mmap()
    // 7. Queue all buffers: VIDIOC_QBUF
    return false;
  }

  bool Start() {
    // TODO: VIDIOC_STREAMON
    return false;
  }

  std::shared_ptr<common::Buffer> CaptureFrame() {
    // TODO: VIDIOC_DQBUF -> wrap in Buffer -> return
    return nullptr;
  }

  void ReleaseFrame(std::shared_ptr<common::Buffer> /*buffer*/) {
    // TODO: VIDIOC_QBUF (return buffer to driver)
  }

  void Stop() {
    // TODO: VIDIOC_STREAMOFF
  }

 private:
  Config config_;
  int fd_;
};

V4L2Camera::V4L2Camera(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

V4L2Camera::~V4L2Camera() = default;
V4L2Camera::V4L2Camera(V4L2Camera&&) noexcept = default;
V4L2Camera& V4L2Camera::operator=(V4L2Camera&&) noexcept = default;

bool V4L2Camera::Initialize() { return impl_->Initialize(); }
bool V4L2Camera::Start() { return impl_->Start(); }

std::shared_ptr<common::Buffer> V4L2Camera::CaptureFrame() {
  return impl_->CaptureFrame();
}

void V4L2Camera::ReleaseFrame(std::shared_ptr<common::Buffer> buffer) {
  impl_->ReleaseFrame(std::move(buffer));
}

void V4L2Camera::Stop() { impl_->Stop(); }

}  // namespace rk_hal
