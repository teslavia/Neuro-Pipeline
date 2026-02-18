#ifndef NEURO_HAL_RGA_PROCESSOR_HPP_
#define NEURO_HAL_RGA_PROCESSOR_HPP_

#include <cstdint>
#include <memory>

#include "neuro/core/buffer.hpp"

namespace neuro::hal {

/**
 * @brief RGA 2D image processor wrapper.
 *
 * Hardware-accelerated image scaling, cropping, rotation, and pixel
 * format conversion using Rockchip RGA engine with zero-copy I/O.
 */
class RGAProcessor {
 public:
  struct Config {
    uint32_t src_width = 1920;
    uint32_t src_height = 1080;
    uint32_t src_format = 0;  // RGA format enum
    uint32_t dst_width = 640;
    uint32_t dst_height = 640;
    uint32_t dst_format = 0;
  };

  explicit RGAProcessor(const Config& config);
  ~RGAProcessor();

  RGAProcessor(const RGAProcessor&) = delete;
  RGAProcessor& operator=(const RGAProcessor&) = delete;

  bool Initialize();

  /// Process input buffer, return output buffer (zero-copy when possible).
  std::shared_ptr<core::Buffer> Process(
      std::shared_ptr<core::Buffer> input);

  /// Resize image to target dimensions.
  std::shared_ptr<core::Buffer> Resize(
      std::shared_ptr<core::Buffer> input,
      uint32_t dst_width, uint32_t dst_height);

  /// Convert pixel format (e.g., NV12 -> RGB888).
  std::shared_ptr<core::Buffer> ConvertFormat(
      std::shared_ptr<core::Buffer> input,
      uint32_t dst_format);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  Config config_;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_RGA_PROCESSOR_HPP_
