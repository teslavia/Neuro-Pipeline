#ifndef AI_INFERENCE_POSTPROCESSOR_BASE_HPP_
#define AI_INFERENCE_POSTPROCESSOR_BASE_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include "common/types.hpp"

namespace ai_inference {

class PostProcessorBase {
 public:
  virtual ~PostProcessorBase() = default;

  virtual std::vector<common::DetectionBox> Process(
      const std::vector<std::vector<float>>& raw_outputs,
      uint32_t original_width, uint32_t original_height) = 0;

  virtual std::string Name() const = 0;
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_POSTPROCESSOR_BASE_HPP_
