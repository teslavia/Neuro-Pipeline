#include "neuro/pipeline/detection_cache.hpp"

#include <algorithm>

namespace neuro::pipeline {

bool DetectionCache::IsNovel(const std::string& class_name, float confidence,
                              float x_min, float y_min,
                              float x_max, float y_max) {
  auto now = std::chrono::steady_clock::now();
  std::lock_guard<std::mutex> lock(mutex_);

  // Remove expired entries
  while (!cache_.empty() && (now - cache_.front().timestamp) > ttl_) {
    cache_.pop_front();
  }

  // Check against existing cache entries
  for (const auto& cached : cache_) {
    if (cached.class_name != class_name) continue;
    float iou = ComputeIoU(cached.x_min, cached.y_min, cached.x_max, cached.y_max,
                            x_min, y_min, x_max, y_max);
    if (iou >= iou_threshold_) {
      return false;  // Duplicate — suppress
    }
  }

  // Novel detection — add to cache
  cache_.push_back({class_name, confidence, x_min, y_min, x_max, y_max, now});
  return true;
}

void DetectionCache::Cleanup() {
  auto now = std::chrono::steady_clock::now();
  std::lock_guard<std::mutex> lock(mutex_);
  while (!cache_.empty() && (now - cache_.front().timestamp) > ttl_) {
    cache_.pop_front();
  }
}

size_t DetectionCache::Size() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return cache_.size();
}

float DetectionCache::ComputeIoU(float ax0, float ay0, float ax1, float ay1,
                                  float bx0, float by0, float bx1, float by1) {
  float ix0 = std::max(ax0, bx0);
  float iy0 = std::max(ay0, by0);
  float ix1 = std::min(ax1, bx1);
  float iy1 = std::min(ay1, by1);

  float inter_w = std::max(0.0f, ix1 - ix0);
  float inter_h = std::max(0.0f, iy1 - iy0);
  float inter_area = inter_w * inter_h;

  float area_a = (ax1 - ax0) * (ay1 - ay0);
  float area_b = (bx1 - bx0) * (by1 - by0);
  float union_area = area_a + area_b - inter_area;

  if (union_area <= 0.0f) return 0.0f;
  return inter_area / union_area;
}

}  // namespace data_processing
