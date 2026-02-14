#include "common/yolo_postprocess.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <numeric>

namespace ai_inference {

namespace {

inline float Sigmoid(float x) {
  return 1.0f / (1.0f + std::exp(-x));
}

// YOLOv5 anchors (COCO pretrained)
constexpr float kAnchors[3][6] = {
    {10, 13, 16, 30, 33, 23},       // P3/8  (80×80)
    {30, 61, 62, 45, 59, 119},      // P4/16 (40×40)
    {116, 90, 156, 198, 373, 326},  // P5/32 (20×20)
};
constexpr int kStrides[3] = {8, 16, 32};
constexpr int kNumAnchors = 3;

}  // namespace

YOLOPostProcessor::YOLOPostProcessor(const Config& config)
    : config_(config) {
  LoadClassNames();
}

std::vector<common::DetectionBox> YOLOPostProcessor::Process(
    const std::vector<std::vector<float>>& raw_outputs,
    uint32_t original_width, uint32_t original_height) {
  if (raw_outputs.empty()) return {};

  std::vector<common::DetectionBox> candidates;
  const int nc = static_cast<int>(config_.num_classes);
  const int prop_size = 5 + nc;  // x, y, w, h, obj_conf, class_scores...

  // Process each scale (3 output heads for YOLOv5)
  for (size_t s = 0; s < raw_outputs.size() && s < 3; ++s) {
    const auto& output = raw_outputs[s];
    int grid_w = static_cast<int>(config_.input_width) / kStrides[s];
    int grid_h = static_cast<int>(config_.input_height) / kStrides[s];
    int grid_len = grid_h * grid_w;
    int expected_size = grid_len * kNumAnchors * prop_size;

    if (static_cast<int>(output.size()) != expected_size) continue;

    // RKNN NCHW layout: output[(anchor * prop_size + channel) * grid_len + y * grid_w + x]
    // Values are already dequantized (want_float=1) and post-sigmoid from RKNN conversion.
    for (int a = 0; a < kNumAnchors; ++a) {
      int base = a * prop_size * grid_len;

      for (int y = 0; y < grid_h; ++y) {
        for (int x = 0; x < grid_w; ++x) {
          int pos = y * grid_w + x;

          float obj_conf = output[base + 4 * grid_len + pos];
          if (obj_conf < config_.confidence_threshold) continue;

          // Find best class
          int best_class = 0;
          float best_score = -1.0f;
          for (int c = 0; c < nc; ++c) {
            float score = output[base + (5 + c) * grid_len + pos];
            if (score > best_score) {
              best_score = score;
              best_class = c;
            }
          }

          float confidence = obj_conf * best_score;
          if (confidence < config_.confidence_threshold) continue;

          // Decode bbox (RKNN YOLOv5: values already post-sigmoid)
          float bx = output[base + 0 * grid_len + pos];
          float by = output[base + 1 * grid_len + pos];
          float bw = output[base + 2 * grid_len + pos];
          float bh = output[base + 3 * grid_len + pos];

          float cx = (bx * 2.0f - 0.5f + x) * kStrides[s];
          float cy = (by * 2.0f - 0.5f + y) * kStrides[s];
          float w = std::pow(bw * 2.0f, 2.0f) * kAnchors[s][a * 2];
          float h = std::pow(bh * 2.0f, 2.0f) * kAnchors[s][a * 2 + 1];

          // Convert to xyxy in pixel coordinates
          float x_min = (cx - w / 2.0f) / config_.input_width;
          float y_min = (cy - h / 2.0f) / config_.input_height;
          float x_max = (cx + w / 2.0f) / config_.input_width;
          float y_max = (cy + h / 2.0f) / config_.input_height;

          // Clamp to [0, 1]
          x_min = std::max(0.0f, std::min(1.0f, x_min));
          y_min = std::max(0.0f, std::min(1.0f, y_min));
          x_max = std::max(0.0f, std::min(1.0f, x_max));
          y_max = std::max(0.0f, std::min(1.0f, y_max));

          std::string name = (best_class < static_cast<int>(class_names_.size()))
                                 ? class_names_[best_class]
                                 : "class_" + std::to_string(best_class);

          candidates.push_back({static_cast<uint32_t>(best_class), name,
                                confidence, x_min, y_min, x_max, y_max});
        }
      }
    }
  }

  return NMS(candidates, config_.nms_threshold);
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
  // Try loading from external file first
  if (!config_.class_names_file.empty()) {
    std::ifstream file(config_.class_names_file);
    if (file.is_open()) {
      class_names_.clear();
      std::string line;
      while (std::getline(file, line)) {
        // Trim whitespace
        auto start = line.find_first_not_of(" \t\r\n");
        if (start == std::string::npos) continue;
        auto end = line.find_last_not_of(" \t\r\n");
        class_names_.push_back(line.substr(start, end - start + 1));
      }
      if (!class_names_.empty()) return;
    }
  }

  // Fallback: hardcoded COCO 80 class names
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
