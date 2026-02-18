#include "neuro/pipeline/temporal_tracker.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "neuro/core/logger.hpp"

namespace neuro::pipeline {

TemporalTracker::TemporalTracker(const Config& config) : config_(config) {}

std::vector<uint64_t> TemporalTracker::Update(
    const std::vector<neuro::core::DetectionBox>& detections, uint64_t frame_id) {
  std::vector<uint64_t> assigned_ids(detections.size(), 0);
  const size_t num_existing_tracks = tracks_.size();
  std::vector<bool> track_matched(num_existing_tracks, false);

  // Greedy IoU matching: for each detection, find best matching track
  for (size_t d = 0; d < detections.size(); ++d) {
    float best_iou = 0.0f;
    size_t best_idx = 0;
    bool found = false;

    for (size_t t = 0; t < num_existing_tracks; ++t) {
      if (track_matched[t]) continue;
      float iou = ComputeIoU(detections[d], tracks_[t]);
      if (iou > best_iou) {
        best_iou = iou;
        best_idx = t;
        found = true;
      }
    }

    if (found && best_iou >= config_.iou_threshold) {
      // Update existing track
      auto& track = tracks_[best_idx];
      track.class_name = detections[d].class_name;
      track.confidence = detections[d].confidence;
      track.x_min = detections[d].x_min;
      track.y_min = detections[d].y_min;
      track.x_max = detections[d].x_max;
      track.y_max = detections[d].y_max;
      track.last_seen_frame = frame_id;
      track.consecutive_frames++;

      auto center = Center(track.x_min, track.y_min, track.x_max, track.y_max);
      track.trajectory.push_back(center);
      if (static_cast<int>(track.trajectory.size()) > config_.trajectory_length) {
        track.trajectory.pop_front();
      }

      track_matched[best_idx] = true;
      assigned_ids[d] = track.track_id;
    } else {
      // Create new track
      TrackedObject new_track;
      new_track.track_id = next_track_id_++;
      new_track.class_name = detections[d].class_name;
      new_track.confidence = detections[d].confidence;
      new_track.x_min = detections[d].x_min;
      new_track.y_min = detections[d].y_min;
      new_track.x_max = detections[d].x_max;
      new_track.y_max = detections[d].y_max;
      new_track.first_seen_frame = frame_id;
      new_track.last_seen_frame = frame_id;
      new_track.consecutive_frames = 1;

      auto center = Center(new_track.x_min, new_track.y_min,
                           new_track.x_max, new_track.y_max);
      new_track.trajectory.push_back(center);

      assigned_ids[d] = new_track.track_id;
      tracks_.push_back(std::move(new_track));
    }
  }

  // Remove tracks not seen for max_lost_frames
  tracks_.erase(
      std::remove_if(tracks_.begin(), tracks_.end(),
                     [&](const TrackedObject& t) {
                       return (frame_id > t.last_seen_frame) &&
                              (static_cast<int>(frame_id - t.last_seen_frame) >
                               config_.max_lost_frames);
                     }),
      tracks_.end());

  return assigned_ids;
}

std::vector<std::pair<uint64_t, BehaviorType>>
TemporalTracker::DetectBehaviors() const {
  std::vector<std::pair<uint64_t, BehaviorType>> behaviors;

  for (const auto& track : tracks_) {
    // Loitering: stationary for extended time
    if (track.consecutive_frames >= config_.loiter_frames &&
        track.trajectory.size() >= 2) {
      float dx = track.trajectory.back().first - track.trajectory.front().first;
      float dy = track.trajectory.back().second - track.trajectory.front().second;
      float displacement = std::sqrt(dx * dx + dy * dy);
      if (displacement < config_.running_speed_threshold *
                             static_cast<float>(track.trajectory.size())) {
        behaviors.emplace_back(track.track_id, BehaviorType::kLoitering);
        continue;
      }
    }

    // Running: high average speed
    if (track.trajectory.size() >= 2) {
      float total_speed = 0.0f;
      for (size_t i = 1; i < track.trajectory.size(); ++i) {
        float dx = track.trajectory[i].first - track.trajectory[i - 1].first;
        float dy = track.trajectory[i].second - track.trajectory[i - 1].second;
        total_speed += std::sqrt(dx * dx + dy * dy);
      }
      float avg_speed = total_speed /
                        static_cast<float>(track.trajectory.size() - 1);
      if (avg_speed > config_.running_speed_threshold) {
        behaviors.emplace_back(track.track_id, BehaviorType::kRunning);
        continue;
      }
    }

    // Lingering: gaps in observation (first_seen much earlier than
    // consecutive_frames suggests)
    if (track.consecutive_frames > 0 &&
        track.last_seen_frame > track.first_seen_frame) {
      int expected_frames = static_cast<int>(
          track.last_seen_frame - track.first_seen_frame) + 1;
      if (track.consecutive_frames < expected_frames / 2) {
        behaviors.emplace_back(track.track_id, BehaviorType::kLingering);
        continue;
      }
    }
  }

  return behaviors;
}

const TrackedObject* TemporalTracker::GetTrack(uint64_t track_id) const {
  for (const auto& track : tracks_) {
    if (track.track_id == track_id) return &track;
  }
  return nullptr;
}

const std::vector<TrackedObject>& TemporalTracker::GetActiveTracks() const {
  return tracks_;
}

size_t TemporalTracker::ActiveTrackCount() const {
  return tracks_.size();
}

float TemporalTracker::ComputeIoU(const neuro::core::DetectionBox& a,
                                   const TrackedObject& b) {
  float inter_x_min = std::max(a.x_min, b.x_min);
  float inter_y_min = std::max(a.y_min, b.y_min);
  float inter_x_max = std::min(a.x_max, b.x_max);
  float inter_y_max = std::min(a.y_max, b.y_max);

  float inter_w = std::max(0.0f, inter_x_max - inter_x_min);
  float inter_h = std::max(0.0f, inter_y_max - inter_y_min);
  float inter_area = inter_w * inter_h;

  float area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min);
  float area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min);
  float union_area = area_a + area_b - inter_area;

  if (union_area <= 0.0f) return 0.0f;
  return inter_area / union_area;
}

std::pair<float, float> TemporalTracker::Center(float x_min, float y_min,
                                                 float x_max, float y_max) {
  return {(x_min + x_max) / 2.0f, (y_min + y_max) / 2.0f};
}

}  // namespace data_processing
