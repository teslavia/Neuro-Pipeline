#include "neuro/hal/mpp_decoder.hpp"

#include <cstring>
#include <iostream>
#include <vector>

#ifndef USE_MOCK_HAL

// ============================================================================
// Real MPP implementation (Linux/RK3588)
// ============================================================================
#include <rockchip/rk_mpi.h>
#include <rockchip/mpp_buffer.h>
#include <rockchip/mpp_frame.h>
#include <rockchip/mpp_packet.h>

namespace {

/// Buffer wrapping an MPP decoded frame. Holds MppFrame reference to keep
/// the underlying buffer alive until released.
class MPPFrameBuffer : public neuro::core::Buffer {
 public:
  MPPFrameBuffer(MppFrame frame, void* data, size_t size, int fd)
      : frame_(frame), data_(data), size_(size), fd_(fd), metadata_{} {}

  ~MPPFrameBuffer() override {
    if (frame_) {
      mpp_frame_deinit(&frame_);
    }
  }

  void* Data() override { return data_; }
  size_t Size() const override { return size_; }
  int GetDMABufFd() const override { return fd_; }
  const Metadata& GetMetadata() const override { return metadata_; }
  void SetMetadata(const Metadata& meta) override { metadata_ = meta; }
  void SyncForDevice(bool /*for_device*/) override {}

 private:
  MppFrame frame_;
  void* data_;
  size_t size_;
  int fd_;
  Metadata metadata_;
};

}  // namespace

namespace neuro::hal {

class MPPDecoder::Impl {
 public:
  explicit Impl(const Config& config) : config_(config), ctx_(nullptr), mpi_(nullptr) {}

  ~Impl() {
    if (ctx_) {
      mpp_destroy(ctx_);
      ctx_ = nullptr;
    }
  }

  bool Initialize() {
    MPP_RET ret = mpp_create(&ctx_, &mpi_);
    if (ret != MPP_OK) {
      std::cerr << "[MPP] mpp_create failed: " << ret << std::endl;
      return false;
    }

    // Determine codec type
    MppCodingType coding = MPP_VIDEO_CodingAVC;  // H.264 default
    if (config_.codec == 7) {  // MPP_VIDEO_CodingHEVC
      coding = MPP_VIDEO_CodingHEVC;
    }

    ret = mpp_init(ctx_, MPP_CTX_DEC, coding);
    if (ret != MPP_OK) {
      std::cerr << "[MPP] mpp_init failed: " << ret << std::endl;
      mpp_destroy(ctx_);
      ctx_ = nullptr;
      return false;
    }

    // Enable split mode for frame-level input
    RK_U32 split_mode = 1;
    mpi_->control(ctx_, MPP_DEC_SET_PARSER_SPLIT_MODE, &split_mode);

    std::cout << "[MPP] Decoder initialized (codec=" << coding << ")" << std::endl;
    return true;
  }

  std::shared_ptr<neuro::core::Buffer> Decode(const uint8_t* data, size_t size) {
    if (!ctx_ || !mpi_ || !data || size == 0) return nullptr;

    // Create packet from input data
    MppPacket packet = nullptr;
    mpp_packet_init(&packet, const_cast<uint8_t*>(data), size);
    mpp_packet_set_pts(packet, frame_count_);

    // Send packet to decoder
    MPP_RET ret = mpi_->decode_put_packet(ctx_, packet);
    mpp_packet_deinit(&packet);
    if (ret != MPP_OK) {
      std::cerr << "[MPP] decode_put_packet failed: " << ret << std::endl;
      return nullptr;
    }

    // Try to get decoded frame
    MppFrame frame = nullptr;
    ret = mpi_->decode_get_frame(ctx_, &frame);
    if (ret != MPP_OK || !frame) {
      return nullptr;  // Need more data or not ready yet
    }

    // Check for errors
    if (mpp_frame_get_errinfo(frame) || mpp_frame_get_discard(frame)) {
      mpp_frame_deinit(&frame);
      return nullptr;
    }

    // Extract buffer info
    MppBuffer mpp_buf = mpp_frame_get_buffer(frame);
    if (!mpp_buf) {
      mpp_frame_deinit(&frame);
      return nullptr;
    }

    void* ptr = mpp_buffer_get_ptr(mpp_buf);
    size_t buf_size = mpp_buffer_get_size(mpp_buf);
    int fd = mpp_buffer_get_fd(mpp_buf);

    uint32_t width = mpp_frame_get_width(frame);
    uint32_t height = mpp_frame_get_height(frame);
    uint32_t hor_stride = mpp_frame_get_hor_stride(frame);
    (void)mpp_frame_get_ver_stride(frame);  // Available if needed later

    auto buffer = std::make_shared<MPPFrameBuffer>(frame, ptr, buf_size, fd);

    neuro::core::Buffer::Metadata meta;
    meta.width = width;
    meta.height = height;
    meta.stride = hor_stride;
    meta.format = 0x3231564E;  // NV12 FourCC
    meta.frame_id = frame_count_++;
    buffer->SetMetadata(meta);

    return buffer;
  }

  void Reset() {
    if (mpi_ && ctx_) {
      mpi_->reset(ctx_);
    }
    frame_count_ = 0;
  }

 private:
  Config config_;
  MppCtx ctx_;
  MppApi* mpi_;
  uint64_t frame_count_ = 0;
};

}  // namespace rk_hal

#else  // USE_MOCK_HAL

// ============================================================================
// Mock MPP implementation (returns synthetic NV12 frames)
// ============================================================================
namespace neuro::hal {

namespace {

class MockDecodedBuffer : public neuro::core::Buffer {
 public:
  MockDecodedBuffer(size_t size) : data_(size), metadata_{} {}

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

class MPPDecoder::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    std::cout << "[MPP-Mock] Decoder initialized ("
              << config_.width << "x" << config_.height << ")" << std::endl;
    return true;
  }

  std::shared_ptr<neuro::core::Buffer> Decode(const uint8_t* data, size_t size) {
    if (!data || size == 0) return nullptr;

    // Generate synthetic NV12 frame
    uint32_t y_size = config_.width * config_.height;
    uint32_t total = y_size * 3 / 2;
    auto frame = std::make_shared<MockDecodedBuffer>(total);
    auto& buf = frame->MutableData();

    // Use input data hash as seed for pattern variation
    uint8_t seed = 0;
    for (size_t i = 0; i < std::min(size, size_t(64)); ++i) {
      seed ^= data[i];
    }

    // Y plane: gradient with seed variation
    for (uint32_t i = 0; i < y_size; ++i) {
      buf[i] = static_cast<uint8_t>((i + seed + frame_count_) % 256);
    }
    // UV plane: neutral
    std::memset(buf.data() + y_size, 128, y_size / 2);

    neuro::core::Buffer::Metadata meta;
    meta.width = config_.width;
    meta.height = config_.height;
    meta.stride = config_.width;
    meta.format = 0x3231564E;  // NV12
    meta.frame_id = frame_count_++;
    frame->SetMetadata(meta);

    return frame;
  }

  void Reset() { frame_count_ = 0; }

 private:
  Config config_;
  uint64_t frame_count_ = 0;
};

}  // namespace rk_hal

#endif  // USE_MOCK_HAL

namespace neuro::hal {

MPPDecoder::MPPDecoder(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

MPPDecoder::~MPPDecoder() = default;

bool MPPDecoder::Initialize() { return impl_->Initialize(); }

std::shared_ptr<neuro::core::Buffer> MPPDecoder::Decode(const uint8_t* data, size_t size) {
  return impl_->Decode(data, size);
}

void MPPDecoder::Reset() { impl_->Reset(); }

}  // namespace rk_hal
