#ifndef NEURO_INFERENCE_POSTPROCESSOR_BASE_HPP_
#define NEURO_INFERENCE_POSTPROCESSOR_BASE_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include "neuro/core/types.hpp"

namespace neuro::inference {

class PostProcessorBase {
 public:
  virtual ~PostProcessorBase() = default;

  virtual std::vector<core::DetectionBox> Process(
      const std::vector<std::vector<float>>& raw_outputs,
      uint32_t original_width, uint32_t original_height) = 0;

  virtual std::string Name() const = 0;
};

}  // namespace neuro::inference

#endif  // NEURO_INFERENCE_POSTPROCESSOR_BASE_HPP_
