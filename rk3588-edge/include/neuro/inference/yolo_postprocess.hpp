#ifndef NEURO_INFERENCE_YOLO_POSTPROCESS_HPP_
#define NEURO_INFERENCE_YOLO_POSTPROCESS_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include "neuro/inference/postprocessor_base.hpp"
#include "neuro/core/types.hpp"

namespace neuro::inference {

/**
 * @brief YOLO model post-processing: output parsing + NMS.
 */
class YOLOPostProcessor : public PostProcessorBase {
 public:
  struct Config {
    float confidence_threshold = 0.5f;
    float nms_threshold = 0.45f;
    uint32_t num_classes = 80;  // COCO dataset
    uint32_t input_width = 640;
    uint32_t input_height = 640;
    std::string class_names_file;  // External file, fallback to hardcoded
    std::string anchors_file;      // Reserved for future use
  };

  explicit YOLOPostProcessor(const Config& config);

  /// Process raw model output tensors into detection boxes.
  std::vector<core::DetectionBox> Process(
      const std::vector<std::vector<float>>& raw_outputs,
      uint32_t original_width, uint32_t original_height) override;

  std::string Name() const override { return "YOLOv5"; }

  /// Non-Maximum Suppression.
  static std::vector<core::DetectionBox> NMS(
      std::vector<core::DetectionBox>& boxes,
      float nms_threshold);

  /// Compute IoU between two boxes.
  static float ComputeIoU(const core::DetectionBox& a,
                          const core::DetectionBox& b);

 private:
  Config config_;
  std::vector<std::string> class_names_;

  void LoadClassNames();
};

}  // namespace neuro::inference

#endif  // NEURO_INFERENCE_YOLO_POSTPROCESS_HPP_
