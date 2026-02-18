#ifndef NEURO_INFERENCE_MODEL_CASCADE_HPP_
#define NEURO_INFERENCE_MODEL_CASCADE_HPP_

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "neuro/inference/multi_model_manager.hpp"
#include "neuro/core/types.hpp"

namespace neuro::inference {

/**
 * @brief Configuration for model cascade (two-stage inference).
 *
 * Light model performs fast screening, heavy model does precise analysis
 * only on regions of interest detected by the light model.
 */
struct CascadeConfig {
  std::string light_model_id;    // e.g., "yolov5s" - fast screening
  std::string heavy_model_id;    // e.g., "yolov8s" - precise analysis

  // Trigger conditions for invoking heavy model
  float min_confidence = 0.3f;   // Minimum confidence to consider
  float max_confidence = 0.7f;   // Below this, trigger heavy model
  int min_detections = 1;        // Minimum detections to trigger cascade

  // ROI expansion for heavy model
  float roi_padding = 0.1f;      // Padding around light model's detection (relative)

  // Class filtering (empty = all classes)
  std::vector<int> target_classes;  // Only cascade for these class IDs

  // Performance tuning
  int max_cascade_per_frame = 5;    // Max ROIs to process per frame
  bool merge_results = true;        // Merge light + heavy detections
  float heavy_weight = 0.8f;        // Weight for heavy model when merging (0-1)
};

/**
 * @brief Result of cascade inference.
 */
struct CascadeResult {
  std::vector<core::DetectionBox> light_detections;   // From light model
  std::vector<core::DetectionBox> heavy_detections;   // From heavy model
  std::vector<core::DetectionBox> merged_detections;  // Merged result
  int cascade_count = 0;            // Number of heavy model invocations
  double light_latency_ms = 0;
  double heavy_latency_ms = 0;
  double total_latency_ms = 0;
};

/**
 * @brief Manages two-stage model cascade for efficient inference.
 *
 * Workflow:
 * 1. Light model processes full frame
 * 2. If detections meet trigger conditions, extract ROIs
 * 3. Heavy model processes each ROI
 * 4. Merge results (optionally)
 */
class ModelCascade {
 public:
  explicit ModelCascade(const CascadeConfig& config);

  /**
   * @brief Process a frame through the cascade.
   *
   * @param frame_data Input frame data (RGB, model input size)
   * @param frame_width Original frame width
   * @param frame_height Original frame height
   * @param model_mgr Multi-model manager with light/heavy models loaded
   * @return CascadeResult containing detections and metrics
   */
  CascadeResult ProcessFrame(const uint8_t* frame_data,
                             int frame_width, int frame_height,
                             MultiModelManager* model_mgr);

  /**
   * @brief Check if cascade should be triggered for given detections.
   */
  bool ShouldCascade(const std::vector<core::DetectionBox>& detections) const;

  /**
   * @brief Extract ROI regions from detections.
   *
   * @param frame_data Original frame data (RGB)
   * @param detections Light model detections
   * @param frame_width Original frame width
   * @param frame_height Original frame height
   * @param model_size Target model input size
   * @return Vector of (roi_bounds, roi_image) pairs
   */
  std::vector<std::pair<core::DetectionBox, std::vector<uint8_t>>> ExtractROIs(
      const uint8_t* frame_data,
      const std::vector<core::DetectionBox>& detections,
      int frame_width, int frame_height,
      int model_size) const;

  /**
   * @brief Merge light and heavy model detections.
   */
  std::vector<core::DetectionBox> MergeDetections(
      const std::vector<core::DetectionBox>& light,
      const std::vector<core::DetectionBox>& heavy) const;

  const CascadeConfig& GetConfig() const { return config_; }

 private:
  CascadeConfig config_;

  /**
   * @brief Map detection coordinates from ROI space to original frame space.
   */
  core::DetectionBox MapToOriginalFrame(
      const core::DetectionBox& roi_detection,
      const core::DetectionBox& roi_bounds) const;

  /**
   * @brief Crop and resize ROI from frame.
   */
  std::vector<uint8_t> CropResizeROI(
      const uint8_t* frame_data,
      int frame_width, int frame_height,
      const core::DetectionBox& roi_bounds,
      int target_size) const;
};

}  // namespace neuro::inference

#endif  // NEURO_INFERENCE_MODEL_CASCADE_HPP_
