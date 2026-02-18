#ifndef NEURO_HAL_MPP_DECODER_HPP_
#define NEURO_HAL_MPP_DECODER_HPP_

#include <cstdint>
#include <memory>
#include <string>

#include "neuro/core/buffer.hpp"

namespace neuro::hal {

/**
 * @brief Rockchip MPP hardware video decoder wrapper.
 *
 * Provides hardware-accelerated video decoding with DMA buffer output
 * for zero-copy integration with downstream processors (RGA, NPU).
 */
class MPPDecoder {
 public:
  struct Config {
    uint32_t width = 1920;
    uint32_t height = 1080;
    uint32_t codec = 0;  // MPP codec type (e.g., MPP_VIDEO_CodingAVC)
  };

  explicit MPPDecoder(const Config& config);
  ~MPPDecoder();

  MPPDecoder(const MPPDecoder&) = delete;
  MPPDecoder& operator=(const MPPDecoder&) = delete;

  bool Initialize();
  std::shared_ptr<core::Buffer> Decode(const uint8_t* data, size_t size);
  void Reset();

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  Config config_;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_MPP_DECODER_HPP_
