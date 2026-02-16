#ifndef DATA_PROCESSING_TEMPORAL_TRACKER_HPP_
#define DATA_PROCESSING_TEMPORAL_TRACKER_HPP_

#include <cstdint>
#include <deque>
#include <string>
#include <utility>
#include <vector>

#include "common/types.hpp"

namespace data_processing {

struct TrackedObject {
  uint64_t track_id = 0;
  std::string class_name;
  float confidence = 0.0f;
  float x_min = 0.0f;
  float y_min = 0.0f;
  float x_max = 0.0f;
  float y_max = 0.0f;
  uint64_t first_seen_frame = 0;
  uint64_t last_seen_frame = 0;
  int consecutive_frames = 0;
  std::deque<std::pair<float, float>> trajectory;  // center points history
};

enum class BehaviorType {
  kNone = 0,
  kLoitering,    // object stays in same area for extended time
  kRunning,      // object moves fast
  kLingering,    // object appears, disappears, reappears
  kCrowding,     // many objects in small area
};

class TemporalTracker {
 public:
  struct Config {
    float iou_threshold = 0.3f;
    int max_lost_frames = 30;
    int trajectory_length = 60;  // sliding window size
    int loiter_frames = 150;     // ~5 sec at 30fps
    float running_speed_threshold = 0.05f;  // normalized units/frame
  };

  explicit TemporalTracker(const Config& config);
  TemporalTracker() : TemporalTracker(Config{}) {}

  /// Update tracker with new detections, returns assigned track IDs.
  std::vector<uint64_t> Update(
      const std::vector<common::DetectionBox>& detections,
      uint64_t frame_id);

  /// Check for behavioral patterns.
  std::vector<std::pair<uint64_t, BehaviorType>> DetectBehaviors() const;

  /// Get tracked object by ID.
  const TrackedObject* GetTrack(uint64_t track_id) const;

  /// Get all active tracks.
  const std::vector<TrackedObject>& GetActiveTracks() const;

  size_t ActiveTrackCount() const;

 private:
  static float ComputeIoU(const common::DetectionBox& a,
                           const TrackedObject& b);
  static std::pair<float, float> Center(float x_min, float y_min,
                                         float x_max, float y_max);

  Config config_;
  std::vector<TrackedObject> tracks_;
  uint64_t next_track_id_ = 1;
};

}  // namespace data_processing

#endif  // DATA_PROCESSING_TEMPORAL_TRACKER_HPP_
