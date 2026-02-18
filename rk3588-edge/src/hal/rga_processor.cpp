#include "neuro/hal/rga_processor.hpp"

#include <cstring>
#include <iostream>
#include <vector>

#ifndef USE_MOCK_HAL

// ============================================================================
// Real RGA implementation (Linux/RK3588)
// ============================================================================
#include <rga/im2d.hpp>
#include <rga/im2d_buffer.h>

#include "neuro/hal/drm_allocator.hpp"

namespace {

class RGAOutputBuffer : public neuro::core::Buffer {
 public:
  RGAOutputBuffer(std::shared_ptr<neuro::core::Buffer> backing)
      : backing_(std::move(backing)) {}

  void* Data() override { return backing_->Data(); }
  size_t Size() const override { return backing_->Size(); }
  int GetDMABufFd() const override { return backing_->GetDMABufFd(); }
  const Metadata& GetMetadata() const override { return backing_->GetMetadata(); }
  void SetMetadata(const Metadata& meta) override { backing_->SetMetadata(meta); }
  void SyncForDevice(bool for_device) override { backing_->SyncForDevice(for_device); }

 private:
  std::shared_ptr<neuro::core::Buffer> backing_;
};

}  // namespace

namespace neuro::hal {

class RGAProcessor::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    // RGA im2d API is stateless — no explicit init needed.
    // Allocate a DRM allocator for output buffers.
    allocator_ = std::make_unique<DRMAllocator>();
    if (!allocator_->Initialize()) {
      std::cerr << "[RGA] Failed to initialize DRM allocator for output" << std::endl;
      return false;
    }
    std::cout << "[RGA] Initialized (src=" << config_.src_width << "x"
              << config_.src_height << " dst=" << config_.dst_width << "x"
              << config_.dst_height << ")" << std::endl;
    return true;
  }

  std::shared_ptr<neuro::core::Buffer> Process(std::shared_ptr<neuro::core::Buffer> input) {
    if (!input) return nullptr;

    // Allocate output buffer (RGB888, dst dimensions)
    size_t dst_size = config_.dst_width * config_.dst_height * 3;
    auto dst_buf = allocator_->Allocate(dst_size);
    if (!dst_buf) {
      std::cerr << "[RGA] Failed to allocate output buffer" << std::endl;
      return nullptr;
    }

    // Wrap src buffer for RGA
    rga_buffer_t src = {};
    int src_fd = input->GetDMABufFd();
    if (src_fd >= 0) {
      src = wrapbuffer_fd_t(src_fd, config_.src_width, config_.src_height,
                            config_.src_width, config_.src_height,
                            RK_FORMAT_YCbCr_420_SP);
    } else {
      src = wrapbuffer_virtualaddr_t(input->Data(),
                                      config_.src_width, config_.src_height,
                                      config_.src_width, config_.src_height,
                                      RK_FORMAT_YCbCr_420_SP);
    }

    // Wrap dst buffer for RGA
    rga_buffer_t dst = {};
    int dst_fd = dst_buf->GetDMABufFd();
    if (dst_fd >= 0) {
      dst = wrapbuffer_fd_t(dst_fd, config_.dst_width, config_.dst_height,
                            config_.dst_width, config_.dst_height,
                            RK_FORMAT_RGB_888);
    } else {
      dst = wrapbuffer_virtualaddr_t(dst_buf->Data(),
                                      config_.dst_width, config_.dst_height,
                                      config_.dst_width, config_.dst_height,
                                      RK_FORMAT_RGB_888);
    }

    // Combined resize + color conversion
    IM_STATUS status = imcvtcolor(src, dst,
                                   RK_FORMAT_YCbCr_420_SP, RK_FORMAT_RGB_888,
                                   IM_YUV_TO_RGB_BT601_LIMIT);
    if (status != IM_STATUS_SUCCESS) {
      // Fallback: try resize first, then convert
      std::cerr << "[RGA] imcvtcolor failed (" << status
                << "), trying imresize" << std::endl;
      status = imresize(src, dst);
    }

    if (status != IM_STATUS_SUCCESS) {
      std::cerr << "[RGA] Processing failed: " << status << std::endl;
      return nullptr;
    }

    neuro::core::Buffer::Metadata meta;
    meta.width = config_.dst_width;
    meta.height = config_.dst_height;
    meta.stride = config_.dst_width * 3;
    meta.format = 0x33424752;  // RGB888 FourCC
    meta.timestamp_us = input->GetMetadata().timestamp_us;
    meta.frame_id = input->GetMetadata().frame_id;
    dst_buf->SetMetadata(meta);

    return std::make_shared<RGAOutputBuffer>(std::move(dst_buf));
  }

  std::shared_ptr<neuro::core::Buffer> Resize(
      std::shared_ptr<neuro::core::Buffer> input,
      uint32_t dst_width, uint32_t dst_height) {
    if (!input) return nullptr;

    const auto& src_meta = input->GetMetadata();
    size_t bpp = 3;  // Assume RGB888
    size_t dst_size = dst_width * dst_height * bpp;
    auto dst_buf = allocator_->Allocate(dst_size);
    if (!dst_buf) return nullptr;

    rga_buffer_t src = {};
    int src_fd = input->GetDMABufFd();
    if (src_fd >= 0) {
      src = wrapbuffer_fd_t(src_fd, src_meta.width, src_meta.height,
                            src_meta.width, src_meta.height, RK_FORMAT_RGB_888);
    } else {
      src = wrapbuffer_virtualaddr_t(input->Data(), src_meta.width, src_meta.height,
                                      src_meta.width, src_meta.height, RK_FORMAT_RGB_888);
    }

    rga_buffer_t dst = {};
    int dst_fd = dst_buf->GetDMABufFd();
    if (dst_fd >= 0) {
      dst = wrapbuffer_fd_t(dst_fd, dst_width, dst_height,
                            dst_width, dst_height, RK_FORMAT_RGB_888);
    } else {
      dst = wrapbuffer_virtualaddr_t(dst_buf->Data(), dst_width, dst_height,
                                      dst_width, dst_height, RK_FORMAT_RGB_888);
    }

    IM_STATUS status = imresize(src, dst);
    if (status != IM_STATUS_SUCCESS) {
      std::cerr << "[RGA] Resize failed: " << status << std::endl;
      return nullptr;
    }

    neuro::core::Buffer::Metadata meta;
    meta.width = dst_width;
    meta.height = dst_height;
    meta.stride = dst_width * bpp;
    meta.format = src_meta.format;
    meta.timestamp_us = src_meta.timestamp_us;
    meta.frame_id = src_meta.frame_id;
    dst_buf->SetMetadata(meta);

    return dst_buf;
  }

  std::shared_ptr<neuro::core::Buffer> ConvertFormat(
      std::shared_ptr<neuro::core::Buffer> input, uint32_t dst_format) {
    if (!input) return nullptr;

    const auto& src_meta = input->GetMetadata();
    uint32_t src_rga_fmt = RK_FORMAT_YCbCr_420_SP;
    uint32_t dst_rga_fmt = RK_FORMAT_RGB_888;
    size_t bpp = 3;

    // Map common FourCC to RGA format
    if (dst_format == 0x33424752 || dst_format == static_cast<uint32_t>(RK_FORMAT_RGB_888)) {
      dst_rga_fmt = RK_FORMAT_RGB_888;
      bpp = 3;
    } else if (dst_format == 0x33524742 || dst_format == static_cast<uint32_t>(RK_FORMAT_BGR_888)) {
      dst_rga_fmt = RK_FORMAT_BGR_888;
      bpp = 3;
    }

    size_t dst_size = src_meta.width * src_meta.height * bpp;
    auto dst_buf = allocator_->Allocate(dst_size);
    if (!dst_buf) return nullptr;

    rga_buffer_t src = {};
    int src_fd = input->GetDMABufFd();
    if (src_fd >= 0) {
      src = wrapbuffer_fd_t(src_fd, src_meta.width, src_meta.height,
                            src_meta.width, src_meta.height, src_rga_fmt);
    } else {
      src = wrapbuffer_virtualaddr_t(input->Data(), src_meta.width, src_meta.height,
                                      src_meta.width, src_meta.height, src_rga_fmt);
    }

    rga_buffer_t dst = {};
    int dst_fd = dst_buf->GetDMABufFd();
    if (dst_fd >= 0) {
      dst = wrapbuffer_fd_t(dst_fd, src_meta.width, src_meta.height,
                            src_meta.width, src_meta.height, dst_rga_fmt);
    } else {
      dst = wrapbuffer_virtualaddr_t(dst_buf->Data(), src_meta.width, src_meta.height,
                                      src_meta.width, src_meta.height, dst_rga_fmt);
    }

    IM_STATUS status = imcvtcolor(src, dst, src_rga_fmt, dst_rga_fmt,
                                   IM_YUV_TO_RGB_BT601_LIMIT);
    if (status != IM_STATUS_SUCCESS) {
      std::cerr << "[RGA] ConvertFormat failed: " << status << std::endl;
      return nullptr;
    }

    neuro::core::Buffer::Metadata meta = src_meta;
    meta.stride = src_meta.width * bpp;
    meta.format = dst_format;
    dst_buf->SetMetadata(meta);

    return dst_buf;
  }

 private:
  Config config_;
  std::unique_ptr<DRMAllocator> allocator_;
};

}  // namespace rk_hal

#else  // USE_MOCK_HAL

// ============================================================================
// Mock RGA implementation (CPU software fallback)
// ============================================================================
namespace neuro::hal {

namespace {

class MockRGABuffer : public neuro::core::Buffer {
 public:
  MockRGABuffer(size_t size) : data_(size), metadata_{} {}

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

/// Simple NV12 → RGB888 conversion (BT.601)
void NV12ToRGB(const uint8_t* nv12, uint8_t* rgb,
               uint32_t width, uint32_t height) {
  const uint8_t* y_plane = nv12;
  const uint8_t* uv_plane = nv12 + width * height;

  for (uint32_t row = 0; row < height; ++row) {
    for (uint32_t col = 0; col < width; ++col) {
      int y = y_plane[row * width + col];
      int u = uv_plane[(row / 2) * width + (col & ~1)] - 128;
      int v = uv_plane[(row / 2) * width + (col | 1)] - 128;

      int r = y + ((359 * v) >> 8);
      int g = y - ((88 * u + 183 * v) >> 8);
      int b = y + ((454 * u) >> 8);

      size_t idx = (row * width + col) * 3;
      rgb[idx + 0] = static_cast<uint8_t>(std::max(0, std::min(255, r)));
      rgb[idx + 1] = static_cast<uint8_t>(std::max(0, std::min(255, g)));
      rgb[idx + 2] = static_cast<uint8_t>(std::max(0, std::min(255, b)));
    }
  }
}

/// Simple bilinear resize for RGB888
void ResizeRGB(const uint8_t* src, uint32_t sw, uint32_t sh,
               uint8_t* dst, uint32_t dw, uint32_t dh) {
  for (uint32_t dy = 0; dy < dh; ++dy) {
    for (uint32_t dx = 0; dx < dw; ++dx) {
      float sx = static_cast<float>(dx) * sw / dw;
      float sy = static_cast<float>(dy) * sh / dh;
      uint32_t x0 = std::min(static_cast<uint32_t>(sx), sw - 1);
      uint32_t y0 = std::min(static_cast<uint32_t>(sy), sh - 1);

      size_t src_idx = (y0 * sw + x0) * 3;
      size_t dst_idx = (dy * dw + dx) * 3;
      dst[dst_idx + 0] = src[src_idx + 0];
      dst[dst_idx + 1] = src[src_idx + 1];
      dst[dst_idx + 2] = src[src_idx + 2];
    }
  }
}

}  // namespace

class RGAProcessor::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    std::cout << "[RGA-Mock] Initialized (src=" << config_.src_width << "x"
              << config_.src_height << " dst=" << config_.dst_width << "x"
              << config_.dst_height << ")" << std::endl;
    return true;
  }

  std::shared_ptr<neuro::core::Buffer> Process(std::shared_ptr<neuro::core::Buffer> input) {
    if (!input) return nullptr;

    // Step 1: NV12 → RGB888 at source resolution
    size_t rgb_size = config_.src_width * config_.src_height * 3;
    std::vector<uint8_t> rgb_temp(rgb_size);
    NV12ToRGB(static_cast<const uint8_t*>(input->Data()), rgb_temp.data(),
              config_.src_width, config_.src_height);

    // Step 2: Resize to dst dimensions
    size_t dst_size = config_.dst_width * config_.dst_height * 3;
    auto output = std::make_shared<MockRGABuffer>(dst_size);
    ResizeRGB(rgb_temp.data(), config_.src_width, config_.src_height,
              static_cast<uint8_t*>(output->Data()),
              config_.dst_width, config_.dst_height);

    neuro::core::Buffer::Metadata meta;
    meta.width = config_.dst_width;
    meta.height = config_.dst_height;
    meta.stride = config_.dst_width * 3;
    meta.format = 0x33424752;  // RGB888
    meta.timestamp_us = input->GetMetadata().timestamp_us;
    meta.frame_id = input->GetMetadata().frame_id;
    output->SetMetadata(meta);

    return output;
  }

  std::shared_ptr<neuro::core::Buffer> Resize(
      std::shared_ptr<neuro::core::Buffer> input,
      uint32_t dst_width, uint32_t dst_height) {
    if (!input) return nullptr;

    const auto& src_meta = input->GetMetadata();
    size_t dst_size = dst_width * dst_height * 3;
    auto output = std::make_shared<MockRGABuffer>(dst_size);
    ResizeRGB(static_cast<const uint8_t*>(input->Data()),
              src_meta.width, src_meta.height,
              static_cast<uint8_t*>(output->Data()), dst_width, dst_height);

    neuro::core::Buffer::Metadata meta = src_meta;
    meta.width = dst_width;
    meta.height = dst_height;
    meta.stride = dst_width * 3;
    output->SetMetadata(meta);

    return output;
  }

  std::shared_ptr<neuro::core::Buffer> ConvertFormat(
      std::shared_ptr<neuro::core::Buffer> input, uint32_t dst_format) {
    if (!input) return nullptr;

    const auto& src_meta = input->GetMetadata();
    size_t dst_size = src_meta.width * src_meta.height * 3;
    auto output = std::make_shared<MockRGABuffer>(dst_size);
    NV12ToRGB(static_cast<const uint8_t*>(input->Data()),
              static_cast<uint8_t*>(output->Data()),
              src_meta.width, src_meta.height);

    neuro::core::Buffer::Metadata meta = src_meta;
    meta.stride = src_meta.width * 3;
    meta.format = dst_format;
    output->SetMetadata(meta);

    return output;
  }

 private:
  Config config_;
};

}  // namespace rk_hal

#endif  // USE_MOCK_HAL

namespace neuro::hal {

RGAProcessor::RGAProcessor(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

RGAProcessor::~RGAProcessor() = default;

bool RGAProcessor::Initialize() { return impl_->Initialize(); }

std::shared_ptr<neuro::core::Buffer> RGAProcessor::Process(
    std::shared_ptr<neuro::core::Buffer> input) {
  return impl_->Process(std::move(input));
}

std::shared_ptr<neuro::core::Buffer> RGAProcessor::Resize(
    std::shared_ptr<neuro::core::Buffer> input,
    uint32_t dst_width, uint32_t dst_height) {
  return impl_->Resize(std::move(input), dst_width, dst_height);
}

std::shared_ptr<neuro::core::Buffer> RGAProcessor::ConvertFormat(
    std::shared_ptr<neuro::core::Buffer> input, uint32_t dst_format) {
  return impl_->ConvertFormat(std::move(input), dst_format);
}

}  // namespace rk_hal
