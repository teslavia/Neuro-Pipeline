#ifndef AI_INFERENCE_RKNN_ENGINE_HPP_
#define AI_INFERENCE_RKNN_ENGINE_HPP_

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "common/buffer.hpp"
#include "common/types.hpp"

namespace ai_inference {

/**
 * @brief RKNN NPU inference engine wrapper.
 *
 * Loads quantized .rknn models and executes inference on the RK3588 NPU
 * with zero-copy input/output support via DMA-BUF.
 */
class RKNNEngine {
 public:
  struct Config {
    std::string model_path;
    int core_mask = 0;  // 0=auto, 1=core0, 2=core1, 4=core2, 7=all
    bool zero_copy = true;
  };

  explicit RKNNEngine(const Config& config);
  ~RKNNEngine();

  RKNNEngine(const RKNNEngine&) = delete;
  RKNNEngine& operator=(const RKNNEngine&) = delete;

  bool Initialize();

  /// Run inference on input buffer. Returns raw output tensors.
  bool Infer(std::shared_ptr<common::Buffer> input);

  /// Dynamically set NPU core affinity mask (1=core0, 2=core1, 4=core2, 7=all).
  void SetCoreMask(int mask);

  /// Get output tensor data after inference.
  const std::vector<std::vector<float>>& GetOutputs() const { return outputs_; }

  /// Get model input dimensions.
  uint32_t InputWidth() const { return input_width_; }
  uint32_t InputHeight() const { return input_height_; }
  uint32_t InputChannels() const { return input_channels_; }

  void Release();

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
  Config config_;
  uint32_t input_width_ = 0;
  uint32_t input_height_ = 0;
  uint32_t input_channels_ = 0;
  std::vector<std::vector<float>> outputs_;
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_RKNN_ENGINE_HPP_
