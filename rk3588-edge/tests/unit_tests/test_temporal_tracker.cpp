#include <gtest/gtest.h>

#include <vector>

#include "common/temporal_tracker.hpp"
#include "common/types.hpp"

namespace {

common::DetectionBox MakeBox(const std::string& cls, float conf,
                             float x0, float y0, float x1, float y1) {
  common::DetectionBox box;
  box.class_name = cls;
  box.confidence = conf;
  box.x_min = x0;
  box.y_min = y0;
  box.x_max = x1;
  box.y_max = y1;
  return box;
}

TEST(TemporalTrackerTest, NewDetectionCreatesTrack) {
  data_processing::TemporalTracker tracker;

  std::vector<common::DetectionBox> dets = {
      MakeBox("person", 0.9f, 0.1f, 0.1f, 0.3f, 0.5f)};
  auto ids = tracker.Update(dets, 1);

  ASSERT_EQ(ids.size(), 1u);
  EXPECT_GT(ids[0], 0u);
  EXPECT_EQ(tracker.ActiveTrackCount(), 1u);

  auto* track = tracker.GetTrack(ids[0]);
  ASSERT_NE(track, nullptr);
  EXPECT_EQ(track->class_name, "person");
}

TEST(TemporalTrackerTest, ConsecutiveDetectionsMatchTrack) {
  data_processing::TemporalTracker::Config cfg;
  cfg.iou_threshold = 0.3f;
  data_processing::TemporalTracker tracker(cfg);

  // Frame 1: create track
  std::vector<common::DetectionBox> dets1 = {
      MakeBox("person", 0.9f, 0.1f, 0.1f, 0.3f, 0.5f)};
  auto ids1 = tracker.Update(dets1, 1);

  // Frame 2: slightly shifted box should match same track
  std::vector<common::DetectionBox> dets2 = {
      MakeBox("person", 0.85f, 0.12f, 0.12f, 0.32f, 0.52f)};
  auto ids2 = tracker.Update(dets2, 2);

  ASSERT_EQ(ids2.size(), 1u);
  EXPECT_EQ(ids1[0], ids2[0]);
  EXPECT_EQ(tracker.ActiveTrackCount(), 1u);

  auto* track = tracker.GetTrack(ids2[0]);
  ASSERT_NE(track, nullptr);
  EXPECT_EQ(track->consecutive_frames, 2);
}

TEST(TemporalTrackerTest, TrackLostAfterTimeout) {
  data_processing::TemporalTracker::Config cfg;
  cfg.max_lost_frames = 5;
  data_processing::TemporalTracker tracker(cfg);

  // Frame 1: create track
  std::vector<common::DetectionBox> dets = {
      MakeBox("car", 0.8f, 0.5f, 0.5f, 0.7f, 0.7f)};
  auto ids = tracker.Update(dets, 1);
  EXPECT_EQ(tracker.ActiveTrackCount(), 1u);

  // Frames 2-7: no detections, track should be pruned after max_lost_frames
  for (uint64_t f = 2; f <= 7; ++f) {
    tracker.Update({}, f);
  }
  EXPECT_EQ(tracker.ActiveTrackCount(), 0u);
}

TEST(TemporalTrackerTest, LoiteringDetection) {
  data_processing::TemporalTracker::Config cfg;
  cfg.loiter_frames = 10;
  cfg.running_speed_threshold = 0.05f;
  data_processing::TemporalTracker tracker(cfg);

  // Stationary object for loiter_frames
  for (uint64_t f = 1; f <= 15; ++f) {
    std::vector<common::DetectionBox> dets = {
        MakeBox("person", 0.9f, 0.1f, 0.1f, 0.3f, 0.5f)};
    tracker.Update(dets, f);
  }

  auto behaviors = tracker.DetectBehaviors();
  ASSERT_FALSE(behaviors.empty());
  EXPECT_EQ(behaviors[0].second, data_processing::BehaviorType::kLoitering);
}

TEST(TemporalTrackerTest, RunningDetection) {
  data_processing::TemporalTracker::Config cfg;
  cfg.iou_threshold = 0.01f;  // very low so moving objects still match
  cfg.running_speed_threshold = 0.02f;
  cfg.loiter_frames = 1000;  // disable loitering for this test
  data_processing::TemporalTracker tracker(cfg);

  // Fast-moving object: large displacement each frame
  for (uint64_t f = 0; f < 10; ++f) {
    float offset = static_cast<float>(f) * 0.05f;
    std::vector<common::DetectionBox> dets = {
        MakeBox("person", 0.9f, offset, 0.1f, offset + 0.1f, 0.2f)};
    tracker.Update(dets, f);
  }

  auto behaviors = tracker.DetectBehaviors();
  bool found_running = false;
  for (const auto& [id, btype] : behaviors) {
    if (btype == data_processing::BehaviorType::kRunning) {
      found_running = true;
      break;
    }
  }
  EXPECT_TRUE(found_running);
}

}  // namespace
