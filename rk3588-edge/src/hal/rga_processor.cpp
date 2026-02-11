#include "rk_hal/rga_processor.hpp"

namespace rk_hal {

class RGAProcessor::Impl {
 public:
  explicit Impl(const Config& config) : config_(config) {}
  ~Impl() = default;

  bool Initialize() {
    // TODO: Initialize RGA context
    // 1. Open RGA device
    // 2. Configure default src/dst rects
    return false;
  }

  std::shared_ptr<common::Buffer> Process(std::shared_ptr<common::Buffer> /*input*/) {
    // TODO: Implement RGA processing (combined resize + format conversion)
    // 1. Set src buffer (from input DMA-BUF fd)
    // 2. Allocate dst buffer
    // 3. improcess() or imcopy()/imresize()/imcvtcolor()
    // 4. Return dst buffer
    return nullptr;
  }

  std::shared_ptr<common::Buffer> Resize(
      std::shared_ptr<common::Buffer> /*input*/,
      uint32_t /*dst_width*/, uint32_t /*dst_height*/) {
    // TODO: imresize()
    return nullptr;
  }

  std::shared_ptr<common::Buffer> ConvertFormat(
      std::shared_ptr<common::Buffer> /*input*/,
      uint32_t /*dst_format*/) {
    // TODO: imcvtcolor()
    return nullptr;
  }

 private:
  Config config_;
};

RGAProcessor::RGAProcessor(const Config& config)
    : impl_(std::make_unique<Impl>(config)), config_(config) {}

RGAProcessor::~RGAProcessor() = default;

bool RGAProcessor::Initialize() { return impl_->Initialize(); }

std::shared_ptr<common::Buffer> RGAProcessor::Process(
    std::shared_ptr<common::Buffer> input) {
  return impl_->Process(std::move(input));
}

std::shared_ptr<common::Buffer> RGAProcessor::Resize(
    std::shared_ptr<common::Buffer> input,
    uint32_t dst_width, uint32_t dst_height) {
  return impl_->Resize(std::move(input), dst_width, dst_height);
}

std::shared_ptr<common::Buffer> RGAProcessor::ConvertFormat(
    std::shared_ptr<common::Buffer> input, uint32_t dst_format) {
  return impl_->ConvertFormat(std::move(input), dst_format);
}

}  // namespace rk_hal
