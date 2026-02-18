#include "neuro/inference/yolov8_postprocess.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>

#include "neuro/inference/yolo_postprocess.hpp"  // Reuse NMS

namespace neuro::inference {

namespace {
constexpr int kStrides[3] = {8, 16, 32};
}  // namespace

YOLOv8PostProcessor::YOLOv8PostProcessor(const Config& config)
    : config_(config) {
  LoadClassNames();
}

void YOLOv8PostProcessor::ComputeDFL(const float* tensor, int dfl_len,
                                      float* box) {
  for (int b = 0; b < 4; b++) {
    float exp_sum = 0.0f;
    float acc_sum = 0.0f;
    // Softmax + weighted sum
    for (int i = 0; i < dfl_len; i++) {
      float e = std::exp(tensor[i + b * dfl_len]);
      exp_sum += e;
    }
    for (int i = 0; i < dfl_len; i++) {
      float e = std::exp(tensor[i + b * dfl_len]);
      acc_sum += (e / exp_sum) * i;
    }
    box[b] = acc_sum;
  }
}

std::vector<neuro::core::DetectionBox> YOLOv8PostProcessor::Process(
    const std::vector<std::vector<float>>& raw_outputs,
    uint32_t /*original_width*/, uint32_t /*original_height*/) {
  if (raw_outputs.empty()) return {};

  std::vector<neuro::core::DetectionBox> candidates;
  const int nc = static_cast<int>(config_.num_classes);
  const int dfl_len = config_.dfl_len;

  // YOLOv8 RKNN output: 6 tensors (2 per scale) or 9 (with score_sum).
  // Per scale: box_tensor [1, dfl_len*4, grid_h, grid_w] (NCHW)
  //            score_tensor [1, num_classes, grid_h, grid_w] (NCHW)
  // We handle 6-output (no score_sum) layout.
  int outputs_per_branch = static_cast<int>(raw_outputs.size()) / 3;
  if (outputs_per_branch < 2) return {};

  for (int s = 0; s < 3; ++s) {
    int box_idx = s * outputs_per_branch;
    int score_idx = s * outputs_per_branch + 1;

    if (box_idx >= static_cast<int>(raw_outputs.size()) ||
        score_idx >= static_cast<int>(raw_outputs.size()))
      break;

    const auto& box_tensor = raw_outputs[box_idx];
    const auto& score_tensor = raw_outputs[score_idx];

    int grid_w = static_cast<int>(config_.input_width) / kStrides[s];
    int grid_h = static_cast<int>(config_.input_height) / kStrides[s];
    int grid_len = grid_h * grid_w;

    // Validate tensor sizes
    int expected_box = dfl_len * 4 * grid_len;
    int expected_score = nc * grid_len;
    if (static_cast<int>(box_tensor.size()) != expected_box ||
        static_cast<int>(score_tensor.size()) != expected_score)
      continue;

    for (int i = 0; i < grid_h; ++i) {
      for (int j = 0; j < grid_w; ++j) {
        int offset = i * grid_w + j;

        // Find max class score (no objectness in YOLOv8)
        int max_class_id = -1;
        float max_score = 0.0f;
        for (int c = 0; c < nc; ++c) {
          float score = score_tensor[c * grid_len + offset];
          if (score > config_.confidence_threshold && score > max_score) {
            max_score = score;
            max_class_id = c;
          }
        }

        if (max_class_id < 0) continue;

        // DFL decode box
        float before_dfl[64];  // dfl_len * 4, max 16*4=64
        for (int k = 0; k < dfl_len * 4; ++k) {
          before_dfl[k] = box_tensor[k * grid_len + offset];
        }
        float box[4];
        ComputeDFL(before_dfl, dfl_len, box);

        float x1 = (-box[0] + j + 0.5f) * kStrides[s];
        float y1 = (-box[1] + i + 0.5f) * kStrides[s];
        float x2 = (box[2] + j + 0.5f) * kStrides[s];
        float y2 = (box[3] + i + 0.5f) * kStrides[s];

        // Normalize to [0, 1]
        float iw = static_cast<float>(config_.input_width);
        float ih = static_cast<float>(config_.input_height);
        float x_min = std::max(0.0f, std::min(1.0f, x1 / iw));
        float y_min = std::max(0.0f, std::min(1.0f, y1 / ih));
        float x_max = std::max(0.0f, std::min(1.0f, x2 / iw));
        float y_max = std::max(0.0f, std::min(1.0f, y2 / ih));

        std::string name =
            (max_class_id < static_cast<int>(class_names_.size()))
                ? class_names_[max_class_id]
                : "class_" + std::to_string(max_class_id);

        candidates.push_back({static_cast<uint32_t>(max_class_id), name,
                              max_score, x_min, y_min, x_max, y_max});
      }
    }
  }

  return YOLOPostProcessor::NMS(candidates, config_.nms_threshold);
}

void YOLOv8PostProcessor::LoadClassNames() {
  if (!config_.class_names_file.empty()) {
    std::ifstream file(config_.class_names_file);
    if (file.is_open()) {
      class_names_.clear();
      std::string line;
      while (std::getline(file, line)) {
        auto start = line.find_first_not_of(" \t\r\n");
        if (start == std::string::npos) continue;
        auto end = line.find_last_not_of(" \t\r\n");
        class_names_.push_back(line.substr(start, end - start + 1));
      }
      if (!class_names_.empty()) return;
    }
  }

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
