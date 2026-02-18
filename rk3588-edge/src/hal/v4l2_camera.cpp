#include "rk_hal/v4l2_camera.hpp"

#include <chrono>
#include <cstring>
#include <iostream>
#include <vector>

#ifndef USE_MOCK_HAL

// ============================================================================
// Real V4L2 implementation (Linux/RK3588)
// ============================================================================
#include <fcntl.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <linux/videodev2.h>

namespace rk_hal {

namespace {

/// Buffer wrapping a V4L2 MMAP buffer.
class V4L2MmapBuffer : public common::Buffer {
 public:
  V4L2MmapBuffer(void* data, size_t size, uint32_t index)
      : data_(data), size_(size), index_(index), metadata_{} {}

  void* Data() override { return data_; }
  size_t Size() const override { return size_; }
  int GetDMABufFd() const override { return -1; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }
  void SyncForDevice(bool /*for_device*/) override {}
  uint32_t Index() const { return index_; }

 private:
  void* data_;
  size_t size_;
  uint32_t index_;
  Metadata metadata_;
};

}  // namespace

class V4L2Camera::Impl {
 public:
  explicit Impl(const Config& config) : config_(config), fd_(-1), streaming_(false) {}

  ~Impl() {
    Stop();
    for (auto& buf : mmap_buffers_) {
      if (buf.start && buf.start != MAP_FAILED) {
        munmap(buf.start, buf.length);
      }
    }
    if (fd_ >= 0) {
      close(fd_);
      fd_ = -1;
    }
  }

  bool Initialize() {
    fd_ = open(config_.device_path.c_str(), O_RDWR);
    if (fd_ < 0) {
      std::cerr << "[V4L2] Failed to open " << config_.device_path
                << ": " << strerror(errno) << std::endl;
      return false;
    }

    // Query capabilities
    struct v4l2_capability cap = {};
    if (ioctl(fd_, VIDIOC_QUERYCAP, &cap) < 0) {
      std::cerr << "[V4L2] QUERYCAP failed" << std::endl;
      return false;
    }

    // Use device_caps if V4L2_CAP_DEVICE_CAPS is set (kernel 3.3+)
    __u32 caps = cap.capabilities;
    if (caps & V4L2_CAP_DEVICE_CAPS) {
      caps = cap.device_caps;
    }

    if (!(caps & V4L2_CAP_VIDEO_CAPTURE)) {
      std::cerr << "[V4L2] Device does not support capture (caps=0x" << std::hex << caps << std::dec << ")" << std::endl;
      return false;
    }
    if (!(caps & V4L2_CAP_STREAMING)) {
      std::cerr << "[V4L2] Device does not support streaming" << std::endl;
      return false;
    }
    std::cout << "[V4L2] Device: " << cap.card << std::endl;

    // Set format (NV12)
    struct v4l2_format fmt = {};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = config_.width;
    fmt.fmt.pix.height = config_.height;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (ioctl(fd_, VIDIOC_S_FMT, &fmt) < 0) {
      std::cerr << "[V4L2] S_FMT failed: " << strerror(errno) << std::endl;
      return false;
    }
    actual_width_ = fmt.fmt.pix.width;
    actual_height_ = fmt.fmt.pix.height;
    frame_size_ = fmt.fmt.pix.sizeimage;
    std::cout << "[V4L2] Format: " << actual_width_ << "x" << actual_height_
              << " sizeimage=" << frame_size_ << std::endl;

    // Set frame rate
    struct v4l2_streamparm parm = {};
    parm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator = 1;
    parm.parm.capture.timeperframe.denominator = config_.fps;
    ioctl(fd_, VIDIOC_S_PARM, &parm);  // Best-effort, not all drivers support

    // Request MMAP buffers
    struct v4l2_requestbuffers req = {};
    req.count = config_.buffer_count;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd_, VIDIOC_REQBUFS, &req) < 0) {
      std::cerr << "[V4L2] REQBUFS failed: " << strerror(errno) << std::endl;
      return false;
    }

    // Map buffers
    mmap_buffers_.resize(req.count);
    for (uint32_t i = 0; i < req.count; ++i) {
      struct v4l2_buffer buf = {};
      buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
      buf.memory = V4L2_MEMORY_MMAP;
      buf.index = i;
      if (ioctl(fd_, VIDIOC_QUERYBUF, &buf) < 0) {
        std::cerr << "[V4L2] QUERYBUF failed for index " << i << std::endl;
        return false;
      }
      mmap_buffers_[i].length = buf.length;
      mmap_buffers_[i].start = mmap(nullptr, buf.length,
                                     PROT_READ | PROT_WRITE, MAP_SHARED,
                                     fd_, buf.m.offset);
      if (mmap_buffers_[i].start == MAP_FAILED) {
        std::cerr << "[V4L2] mmap failed for index " << i << std::endl;
        return false;
      }
    }

    // Queue all buffers
    for (uint32_t i = 0; i < req.count; ++i) {
      struct v4l2_buffer buf = {};
      buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
      buf.memory = V4L2_MEMORY_MMAP;
      buf.index = i;
      if (ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
        std::cerr << "[V4L2] QBUF failed for index " << i << std::endl;
        return false;
      }
    }

    std::cout << "[V4L2] Initialized with " << req.count << " buffers" << std::endl;
    return true;
  }

  bool Start() {
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(fd_, VIDIOC_STREAMON, &type) < 0) {
      std::cerr << "[V4L2] STREAMON failed: " << strerror(errno) << std::endl;
      return false;
    }
    streaming_ = true;
    frame_id_ = 0;
    std::cout << "[V4L2] Streaming started" << std::endl;
    return true;
  }

  std::shared_ptr<common::Buffer> CaptureFrame() {
    if (!streaming_) return nullptr;

    // Poll with 2-second timeout
    struct pollfd pfd = {fd_, POLLIN, 0};
    int ret = poll(&pfd, 1, 2000);
    if (ret <= 0) {
      if (ret == 0) std::cerr << "[V4L2] Poll timeout" << std::endl;
      return nullptr;
    }

    // Dequeue buffer
    struct v4l2_buffer buf = {};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
      std::cerr << "[V4L2] DQBUF failed: " << strerror(errno) << std::endl;
      return nullptr;
    }

    auto frame = std::make_shared<V4L2MmapBuffer>(
        mmap_buffers_[buf.index].start, buf.bytesused, buf.index);

    common::Buffer::Metadata meta;
    meta.width = actual_width_;
    meta.height = actual_height_;
    meta.stride = actual_width_;  // NV12 Y-plane stride
    meta.format = V4L2_PIX_FMT_NV12;
    meta.timestamp_us = buf.timestamp.tv_sec * 1000000ULL + buf.timestamp.tv_usec;
    meta.frame_id = frame_id_++;
    frame->SetMetadata(meta);

    return frame;
  }

  void ReleaseFrame(std::shared_ptr<common::Buffer> buffer) {
    auto* v4l2_buf = dynamic_cast<V4L2MmapBuffer*>(buffer.get());
    if (!v4l2_buf) return;

    struct v4l2_buffer buf = {};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = v4l2_buf->Index();
    ioctl(fd_, VIDIOC_QBUF, &buf);
  }

  void Stop() {
    if (!streaming_) return;
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(fd_, VIDIOC_STREAMOFF, &type);
    streaming_ = false;
    std::cout << "[V4L2] Streaming stopped" << std::endl;
  }

 private:
  struct MmapBuffer {
    void* start = nullptr;
    size_t length = 0;
  };

  Config config_;
  int fd_;
  bool streaming_;
  uint32_t actual_width_ = 0;
  uint32_t actual_height_ = 0;
  uint32_t frame_size_ = 0;
  uint64_t frame_id_ = 0;
  std::vector<MmapBuffer> mmap_buffers_;
};

}  // namespace rk_hal

#else  // USE_MOCK_HAL

// ============================================================================
// Mock V4L2 implementation (generates synthetic NV12 frames)
// ============================================================================
namespace rk_hal {

namespace {

class MockFrameBuffer : public common::Buffer {
 public:
  MockFrameBuffer(size_t size) : data_(size), metadata_{} {}

  void* Data() override { return data_.data(); }
  size_t Size() const override { return data_.size(); }
  int GetDMABufFd() const override { return -1; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }
  void SyncForDevice(bool /*for_device*/) override {}

  std::vector<uint8_t>& MutableData() { return data_; }

 private:
  std::vector<uint8_t> data_;
  Metadata metadata_;
};

}  // namespace

class V4L2Camera::Impl {
 public:
  explicit Impl(const Config& config) : config_(config), streaming_(false) {}
  ~Impl() = default;

  bool Initialize() {
    frame_size_ = config_.width * config_.height * 3 / 2;  // NV12
    std::cout << "[V4L2-Mock] Initialized " << config_.width << "x"
              << config_.height << " NV12" << std::endl;
    return true;
  }

  bool Start() {
    streaming_ = true;
    frame_id_ = 0;
    std::cout << "[V4L2-Mock] Streaming started" << std::endl;
    return true;
  }

  std::shared_ptr<common::Buffer> CaptureFrame() {
    if (!streaming_) return nullptr;

    auto frame = std::make_shared<MockFrameBuffer>(frame_size_);
    auto& data = frame->MutableData();

    // Generate synthetic NV12: gradient Y-plane + neutral UV
    uint32_t y_size = config_.width * config_.height;
    for (uint32_t y = 0; y < config_.height; ++y) {
      for (uint32_t x = 0; x < config_.width; ++x) {
        // Gradient with frame-varying pattern
        data[y * config_.width + x] = static_cast<uint8_t>(
            (x + y + frame_id_ * 3) % 256);
      }
    }
    // UV plane: neutral gray (128)
    std::memset(data.data() + y_size, 128, y_size / 2);

    common::Buffer::Metadata meta;
    meta.width = config_.width;
    meta.height = config_.height;
    meta.stride = config_.width;
    meta.format = 0x3231564E;  // NV12 FourCC
    meta.timestamp_us = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    meta.frame_id = frame_id_++;
    frame->SetMetadata(meta);

    return frame;
  }

  void ReleaseFrame(std::shared_ptr<common::Buffer> /*buffer*/) {}

  void Stop() {
    streaming_ = false;
    std::cout << "[V4L2-Mock] Streaming stopped" << std::endl;
  }

 private:
  Config config_;
  bool streaming_;
  uint32_t frame_size_ = 0;
  uint64_t frame_id_ = 0;
};

}  // namespace rk_hal

#endif  // USE_MOCK_HAL

namespace rk_hal {

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
