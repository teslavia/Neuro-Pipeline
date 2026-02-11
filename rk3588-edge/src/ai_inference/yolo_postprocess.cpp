#include "common/yolo_postprocess.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace ai_inference {

YOLOPostProcessor::YOLOPostProcessor(const Config& config)
    : config_(config) {
  LoadClassNames();
}

std::vector<common::DetectionBox> YOLOPostProcessor::Process(
    const std::vector<std::vector<float>>& /*raw_outputs*/,
    uint32_t /*original_width*/, uint32_t /*original_height*/) {
  // TODO: Implement YOLO output parsing
  // 1. Decode raw output tensors (depends on YOLO version: v5/v8/v10)
  // 2. Apply sigmoid to objectness and class scores
  // 3. Filter by confidence_threshold
  // 4. Convert box format (cx, cy, w, h) -> (x_min, y_min, x_max, y_max)
  // 5. Scale coordinates to original image dimensions
  // 6. Normalize to [0, 1]
  // 7. Apply NMS
  return {};
}

float YOLOPostProcessor::ComputeIoU(const common::DetectionBox& a,
                                     const common::DetectionBox& b) {
  float x1 = std::max(a.x_min, b.x_min);
  float y1 = std::max(a.y_min, b.y_min);
  float x2 = std::min(a.x_max, b.x_max);
  float y2 = std::min(a.y_max, b.y_max);

  float intersection = std::max(0.0f, x2 - x1) * std::max(0.0f, y2 - y1);

  float area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min);
  float area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min);
  float union_area = area_a + area_b - intersection;

  if (union_area <= 0.0f) return 0.0f;
  return intersection / union_area;
}

std::vector<common::DetectionBox> YOLOPostProcessor::NMS(
    std::vector<common::DetectionBox>& boxes,
    float nms_threshold) {
  if (boxes.empty()) return {};

  // Sort by confidence (descending)
  std::sort(boxes.begin(), boxes.end(),
            [](const auto& a, const auto& b) {
              return a.confidence > b.confidence;
            });

  std::vector<bool> suppressed(boxes.size(), false);
  std::vector<common::DetectionBox> result;

  for (size_t i = 0; i < boxes.size(); ++i) {
    if (suppressed[i]) continue;

    result.push_back(boxes[i]);

    for (size_t j = i + 1; j < boxes.size(); ++j) {
      if (suppressed[j]) continue;

      if (boxes[i].class_id == boxes[j].class_id &&
          ComputeIoU(boxes[i], boxes[j]) > nms_threshold) {
        suppressed[j] = true;
      }
    }
  }

  return result;
}

void YOLOPostProcessor::LoadClassNames() {
  // COCO 80 class names
  class_names_ = {
      "person",        "bicycle",      "car",           "motorcycle",
      "airplane",      "bus",          "train",         "truck",
      "boat",          "traffic light","fire hydrant",  "stop sign",
      "parking meter", "bench",        "bird",          "cat",
      "dog",           "horse",        "sheep",         "cow",
      "elephant",      "bear",         "zebra",         "giraffe",
      "backpack",      "umbrella",     "handbag",       "tie",
      "suitcase",      "frisbee",      "skis",          "snowboard",
      "sports ball",   "kite",         "baseball bat",  "baseball glove",
      "skateboard",    "surfboard",    "tennis racket", "bottle",
      "wine glass",    "cup",          "fork",          "knife",
      "spoon",         "bowl",         "banana",        "apple",
      "sandwich",      "orange",       "broccoli",      "carrot",
      "hot dog",       "pizza",        "donut",         "cake",
      "chair",         "couch",        "potted plant",  "bed",
      "dining table",  "toilet",       "tv",            "laptop",
      "mouse",         "remote",       "keyboard",      "cell phone",
      "microwave",     "oven",         "toaster",       "sink",
      "refrigerator",  "book",         "clock",         "vase",
      "scissors",      "teddy bear",   "hair drier",    "toothbrush",
  };
}

}  // namespace ai_inference
