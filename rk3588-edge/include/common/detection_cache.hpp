#ifndef COMMON_DETECTION_CACHE_HPP_
#define COMMON_DETECTION_CACHE_HPP_

#include <chrono>
#include <deque>
#include <mutex>
#include <string>

namespace data_processing {

/**
 * @brief IoU-based temporal detection deduplication cache.
 *
 * Suppresses duplicate detections within a TTL window when the IoU
 * between a new detection and a cached one exceeds the threshold.
 */
class DetectionCache {
 public:
  struct Detection {
    std::string class_name;
    float confidence;
    float x_min, y_min, x_max, y_max;
    std::chrono::steady_clock::time_point timestamp;
  };

  explicit DetectionCache(float iou_threshold = 0.5f,
                          double ttl_seconds = 2.0)
      : iou_threshold_(iou_threshold),
        ttl_(std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            std::chrono::duration<double>(ttl_seconds))) {}

  /**
   * @brief Check if a detection is novel (not a duplicate).
   * If novel, it is added to the cache. If duplicate, it is suppressed.
   * @return true if the detection is novel and should be forwarded.
   */
  bool IsNovel(const std::string& class_name, float confidence,
               float x_min, float y_min, float x_max, float y_max);

  /** Remove expired entries from the cache. */
  void Cleanup();

  /** Number of entries currently in the cache. */
  size_t Size() const;

  /** Compute IoU between two bounding boxes. */
  static float ComputeIoU(float ax0, float ay0, float ax1, float ay1,
                           float bx0, float by0, float bx1, float by1);

 private:
  float iou_threshold_;
  std::chrono::steady_clock::duration ttl_;
  std::deque<Detection> cache_;
  mutable std::mutex mutex_;
};

}  // namespace data_processing

#endif  // COMMON_DETECTION_CACHE_HPP_
