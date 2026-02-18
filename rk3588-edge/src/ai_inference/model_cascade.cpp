#include "neuro/inference/model_cascade.hpp"

#include <algorithm>
#include <chrono>
#include <utility>

#include "neuro/core/buffer.hpp"
#include "neuro/core/logger.hpp"

namespace neuro::inference {

ModelCascade::ModelCascade(const CascadeConfig& config)
    : config_(config) {
  LOG_INFO("ModelCascade", "Initialized: light=%s heavy=%s conf_range=[%.2f, %.2f]",
           config.light_model_id.c_str(), config.heavy_model_id.c_str(),
           config.min_confidence, config.max_confidence);
}

bool ModelCascade::ShouldCascade(
    const std::vector<neuro::core::DetectionBox>& detections) const {
  if (detections.empty()) {
    return false;
  }

  int cascade_candidates = 0;

  for (const auto& det : detections) {
    // Filter by class if configured
    if (!config_.target_classes.empty()) {
      if (std::find(config_.target_classes.begin(),
                    config_.target_classes.end(),
                    det.class_id) == config_.target_classes.end()) {
        continue;
      }
    }

    // Check confidence range
    if (det.confidence >= config_.min_confidence &&
        det.confidence < config_.max_confidence) {
      cascade_candidates++;
    }
  }

  return cascade_candidates >= config_.min_detections;
}

std::vector<std::pair<neuro::core::DetectionBox, std::vector<uint8_t>>> ModelCascade::ExtractROIs(
    const uint8_t* frame_data,
    const std::vector<neuro::core::DetectionBox>& detections,
    int frame_width, int frame_height,
    int model_size) const {
  std::vector<std::pair<neuro::core::DetectionBox, std::vector<uint8_t>>> rois;
  int roi_count = 0;

  for (const auto& det : detections) {
    if (roi_count >= config_.max_cascade_per_frame) {
      break;
    }

    // Filter by class and confidence
    if (!config_.target_classes.empty()) {
      if (std::find(config_.target_classes.begin(),
                    config_.target_classes.end(),
                    det.class_id) == config_.target_classes.end()) {
        continue;
      }
    }

    if (det.confidence < config_.min_confidence ||
        det.confidence >= config_.max_confidence) {
      continue;
    }

    auto roi = CropResizeROI(frame_data, frame_width, frame_height,
                            det, model_size);
    if (!roi.empty()) {
      rois.emplace_back(det, std::move(roi));
      roi_count++;
    }
  }

  return rois;
}

std::vector<uint8_t> ModelCascade::CropResizeROI(
    const uint8_t* frame_data,
    int frame_width, int frame_height,
    const neuro::core::DetectionBox& roi_bounds,
    int target_size) const {
  // Convert normalized coordinates to pixel coordinates with padding
  int x1 = static_cast<int>(roi_bounds.x_min * frame_width * (1.0f - config_.roi_padding));
  int y1 = static_cast<int>(roi_bounds.y_min * frame_height * (1.0f - config_.roi_padding));
  int x2 = static_cast<int>(roi_bounds.x_max * frame_width * (1.0f + config_.roi_padding));
  int y2 = static_cast<int>(roi_bounds.y_max * frame_height * (1.0f + config_.roi_padding));

  // Clamp to frame boundaries
  x1 = std::max(0, x1);
  y1 = std::max(0, y1);
  x2 = std::min(frame_width, x2);
  y2 = std::min(frame_height, y2);

  int roi_w = x2 - x1;
  int roi_h = y2 - y1;

  if (roi_w <= 0 || roi_h <= 0) {
    return {};
  }

  // Allocate output buffer (RGB)
  std::vector<uint8_t> roi(target_size * target_size * 3);

  // Simple nearest-neighbor resize
  float scale_x = static_cast<float>(roi_w) / target_size;
  float scale_y = static_cast<float>(roi_h) / target_size;

  for (int dy = 0; dy < target_size; ++dy) {
    for (int dx = 0; dx < target_size; ++dx) {
      int sx = x1 + static_cast<int>(dx * scale_x);
      int sy = y1 + static_cast<int>(dy * scale_y);

      // Clamp source coordinates
      sx = std::min(sx, frame_width - 1);
      sy = std::min(sy, frame_height - 1);

      int src_idx = (sy * frame_width + sx) * 3;
      int dst_idx = (dy * target_size + dx) * 3;

      roi[dst_idx + 0] = frame_data[src_idx + 0];
      roi[dst_idx + 1] = frame_data[src_idx + 1];
      roi[dst_idx + 2] = frame_data[src_idx + 2];
    }
  }

  return roi;
}

neuro::core::DetectionBox ModelCascade::MapToOriginalFrame(
    const neuro::core::DetectionBox& roi_detection,
    const neuro::core::DetectionBox& roi_bounds) const {
  neuro::core::DetectionBox mapped = roi_detection;

  // ROI coordinates are normalized within the cropped region
  // Map back to original frame normalized coordinates
  float roi_x_min = roi_bounds.x_min * (1.0f - config_.roi_padding);
  float roi_y_min = roi_bounds.y_min * (1.0f - config_.roi_padding);
  float roi_x_max = roi_bounds.x_max * (1.0f + config_.roi_padding);
  float roi_y_max = roi_bounds.y_max * (1.0f + config_.roi_padding);

  float roi_width = roi_x_max - roi_x_min;
  float roi_height = roi_y_max - roi_y_min;

  mapped.x_min = roi_x_min + roi_detection.x_min * roi_width;
  mapped.y_min = roi_y_min + roi_detection.y_min * roi_height;
  mapped.x_max = roi_x_min + roi_detection.x_max * roi_width;
  mapped.y_max = roi_y_min + roi_detection.y_max * roi_height;

  // Clamp to [0, 1]
  mapped.x_min = std::max(0.0f, std::min(1.0f, mapped.x_min));
  mapped.y_min = std::max(0.0f, std::min(1.0f, mapped.y_min));
  mapped.x_max = std::max(0.0f, std::min(1.0f, mapped.x_max));
  mapped.y_max = std::max(0.0f, std::min(1.0f, mapped.y_max));

  return mapped;
}

std::vector<neuro::core::DetectionBox> ModelCascade::MergeDetections(
    const std::vector<neuro::core::DetectionBox>& light,
    const std::vector<neuro::core::DetectionBox>& heavy) const {
  if (!config_.merge_results) {
    // Return heavy model results only
    return heavy;
  }

  std::vector<neuro::core::DetectionBox> merged;

  // Add heavy detections with weight
  for (const auto& det : heavy) {
    neuro::core::DetectionBox weighted = det;
    weighted.confidence = det.confidence * config_.heavy_weight;
    merged.push_back(weighted);
  }

  // Add light detections that don't overlap with heavy detections
  for (const auto& l_det : light) {
    bool overlaps = false;
    for (const auto& h_det : heavy) {
      // Simple IoU check
      float xi1 = std::max(l_det.x_min, h_det.x_min);
      float yi1 = std::max(l_det.y_min, h_det.y_min);
      float xi2 = std::min(l_det.x_max, h_det.x_max);
      float yi2 = std::min(l_det.y_max, h_det.y_max);

      float inter_area = std::max(0.0f, xi2 - xi1) * std::max(0.0f, yi2 - yi1);
      float l_area = (l_det.x_max - l_det.x_min) * (l_det.y_max - l_det.y_min);
      float h_area = (h_det.x_max - h_det.x_min) * (h_det.y_max - h_det.y_min);
      float union_area = l_area + h_area - inter_area;

      float iou = (union_area > 0) ? inter_area / union_area : 0;

      if (iou > 0.5f && l_det.class_id == h_det.class_id) {
        overlaps = true;
        break;
      }
    }

    if (!overlaps) {
      merged.push_back(l_det);
    }
  }

  return merged;
}

CascadeResult ModelCascade::ProcessFrame(
    const uint8_t* frame_data,
    int frame_width, int frame_height,
    MultiModelManager* model_mgr) {
  using Clock = std::chrono::steady_clock;

  CascadeResult result;
  auto total_start = Clock::now();

  // Get light model
  auto* light_slot = model_mgr->GetModel(config_.light_model_id);
  if (!light_slot || !light_slot->engine || !light_slot->postprocessor) {
    LOG_ERROR("ModelCascade", "Light model not found: %s",
              config_.light_model_id.c_str());
    return result;
  }

  // Run light model inference
  auto light_start = Clock::now();

  std::vector<neuro::core::DetectionBox> light_dets;
  int model_size = static_cast<int>(light_slot->engine->InputWidth());

  // Create a mapped buffer for the input data
  size_t input_size = model_size * model_size * 3;
  auto input_buffer = neuro::core::BufferFactory::CreateMappedBuffer(
      const_cast<uint8_t*>(frame_data), input_size);

  // Run inference
  if (light_slot->engine->Infer(input_buffer)) {
    auto outputs = light_slot->engine->GetOutputs();
    light_dets = light_slot->postprocessor->Process(
        outputs, frame_width, frame_height);
  }

  auto light_end = Clock::now();
  result.light_latency_ms = std::chrono::duration<double, std::milli>(
      light_end - light_start).count();
  result.light_detections = light_dets;

  // Check if cascade should be triggered
  if (!ShouldCascade(light_dets)) {
    result.merged_detections = light_dets;
    result.total_latency_ms = result.light_latency_ms;
    return result;
  }

  // Get heavy model
  auto* heavy_slot = model_mgr->GetModel(config_.heavy_model_id);
  if (!heavy_slot || !heavy_slot->engine || !heavy_slot->postprocessor) {
    LOG_WARN("ModelCascade", "Heavy model not found: %s, using light results only",
             config_.heavy_model_id.c_str());
    result.merged_detections = light_dets;
    result.total_latency_ms = result.light_latency_ms;
    return result;
  }

  // Extract ROIs and run heavy model
  auto heavy_start = Clock::now();

  int heavy_model_size = static_cast<int>(heavy_slot->engine->InputWidth());
  std::vector<neuro::core::DetectionBox> heavy_dets;

  // Extract ROIs
  auto rois = ExtractROIs(frame_data, light_dets, frame_width, frame_height, heavy_model_size);
  result.cascade_count = static_cast<int>(rois.size());

  // Run heavy model on each ROI
  for (const auto& [roi_bounds, roi_data] : rois) {
    auto roi_buffer = neuro::core::BufferFactory::CreateMappedBuffer(
        const_cast<uint8_t*>(roi_data.data()), roi_data.size());

    if (heavy_slot->engine->Infer(roi_buffer)) {
      auto outputs = heavy_slot->engine->GetOutputs();
      auto roi_dets = heavy_slot->postprocessor->Process(
          outputs, heavy_model_size, heavy_model_size);

      // Map ROI detections back to original frame coordinates
      for (const auto& roi_det : roi_dets) {
        auto mapped = MapToOriginalFrame(roi_det, roi_bounds);
        heavy_dets.push_back(mapped);
      }
    }
  }

  auto heavy_end = Clock::now();
  result.heavy_latency_ms = std::chrono::duration<double, std::milli>(
      heavy_end - heavy_start).count();
  result.heavy_detections = heavy_dets;

  // Merge results
  result.merged_detections = MergeDetections(light_dets, heavy_dets);

  auto total_end = Clock::now();
  result.total_latency_ms = std::chrono::duration<double, std::milli>(
      total_end - total_start).count();

  if (result.cascade_count > 0) {
    LOG_DEBUG("ModelCascade", "Cascade: %d ROIs processed, light=%.1fms heavy=%.1fms total=%.1fms",
              result.cascade_count, result.light_latency_ms, result.heavy_latency_ms,
              result.total_latency_ms);
  }

  return result;
}

}  // namespace ai_inference
