#ifndef AI_INFERENCE_YOLOV8_POSTPROCESS_HPP_
#define AI_INFERENCE_YOLOV8_POSTPROCESS_HPP_

#include <cstdint>
#include <string>
#include <vector>

#include "common/postprocessor_base.hpp"
#include "common/types.hpp"

namespace ai_inference {

/**
 * @brief YOLOv8 anchor-free post-processing with DFL (Distribution Focal Loss) decoding.
 *
 * Key differences from YOLOv5:
 *   - No objectness score — class score is used directly
 *   - Anchor-free: box offsets decoded via DFL instead of anchor scaling
 *   - Output layout: separate box_tensor and score_tensor per scale
 *     (6 outputs for 3 scales, or 9 with score_sum optimization)
 */
class YOLOv8PostProcessor : public PostProcessorBase {
 public:
  struct Config {
    float confidence_threshold = 0.5f;
    float nms_threshold = 0.45f;
    uint32_t num_classes = 80;
    uint32_t input_width = 640;
    uint32_t input_height = 640;
    int dfl_len = 16;  // DFL distribution length (default for YOLOv8)
    std::string class_names_file;
  };

  explicit YOLOv8PostProcessor(const Config& config);

  std::vector<common::DetectionBox> Process(
      const std::vector<std::vector<float>>& raw_outputs,
      uint32_t original_width, uint32_t original_height) override;

  std::string Name() const override { return "YOLOv8"; }

 private:
  Config config_;
  std::vector<std::string> class_names_;

  /// DFL decode: convert distribution tensor to box offset.
  static void ComputeDFL(const float* tensor, int dfl_len, float* box);

  void LoadClassNames();
};

}  // namespace ai_inference

#endif  // AI_INFERENCE_YOLOV8_POSTPROCESS_HPP_
