#include "rk_hal/mpp_decoder.hpp"

namespace rk_hal {

class MPPDecoder::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    // TODO: Implement MPP decoder initialization
    // 1. mpp_create(&ctx_, &mpi_)
    // 2. mpp_init(ctx_, MPP_CTX_DEC, config_.codec)
    // 3. Configure decoder parameters
    return false;
  }

  std::shared_ptr<common::Buffer> Decode(const uint8_t* /*data*/, size_t /*size*/) {
    // TODO: Implement MPP decoding
    // 1. Create MppPacket from input data
    // 2. mpi_->decode_put_packet(ctx_, packet)
    // 3. mpi_->decode_get_frame(ctx_, &frame)
    // 4. Extract DMA-BUF fd from MppFrame
    // 5. Wrap in Buffer and return
    return nullptr;
  }

  void Reset() {
    // TODO: mpi_->reset(ctx_)
  }

 private:
  Config config_;
  // TODO: MppCtx ctx_ = nullptr;
  // TODO: MppApi* mpi_ = nullptr;
};

MPPDecoder::MPPDecoder(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

MPPDecoder::~MPPDecoder() = default;

bool MPPDecoder::Initialize() { return impl_->Initialize(); }

std::shared_ptr<common::Buffer> MPPDecoder::Decode(const uint8_t* data, size_t size) {
  return impl_->Decode(data, size);
}

void MPPDecoder::Reset() { impl_->Reset(); }

}  // namespace rk_hal
