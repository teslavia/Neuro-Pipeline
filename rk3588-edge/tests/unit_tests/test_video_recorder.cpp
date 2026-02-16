#include <gtest/gtest.h>
#include "common/video_recorder.hpp"

TEST(VideoRecorderTest, BufferManagement) {
  common::VideoRecorder::Config cfg;
  cfg.enabled = true;
  cfg.pre_seconds = 1.0;
  cfg.post_seconds = 2.0;
  cfg.fps = 10;

  common::VideoRecorder recorder(cfg);
  EXPECT_EQ(recorder.BufferSize(), 0u);

  // Push 15 frames (buffer max = 1.0 * 10 = 10)
  for (int i = 0; i < 15; ++i) {
    auto buf = std::make_shared<common::Buffer>(100);
    recorder.PushFrame(buf);
  }
  EXPECT_EQ(recorder.BufferSize(), 10u);
}

TEST(VideoRecorderTest, TriggerRecording) {
  common::VideoRecorder::Config cfg;
  cfg.enabled = true;
  cfg.pre_seconds = 0.5;
  cfg.post_seconds = 0.5;
  cfg.fps = 10;

  common::VideoRecorder recorder(cfg);
  EXPECT_FALSE(recorder.IsRecording());

  // Fill buffer
  for (int i = 0; i < 5; ++i) {
    recorder.PushFrame(std::make_shared<common::Buffer>(100));
  }

  recorder.TriggerRecording("person_detected");
  EXPECT_TRUE(recorder.IsRecording());
}

TEST(VideoRecorderTest, RecordingCompletes) {
  common::VideoRecorder::Config cfg;
  cfg.enabled = true;
  cfg.pre_seconds = 0.1;
  cfg.post_seconds = 0.3;
  cfg.fps = 10;  // post = 3 frames

  common::VideoRecorder recorder(cfg);
  recorder.TriggerRecording("test_event");
  EXPECT_TRUE(recorder.IsRecording());
  EXPECT_EQ(recorder.RecordingsCompleted(), 0u);

  // Push post_seconds * fps = 3 frames + 1 to complete
  for (int i = 0; i < 4; ++i) {
    recorder.PushFrame(std::make_shared<common::Buffer>(100));
  }
  EXPECT_FALSE(recorder.IsRecording());
  EXPECT_EQ(recorder.RecordingsCompleted(), 1u);
}

TEST(VideoRecorderTest, DoubleTriggerIgnored) {
  common::VideoRecorder::Config cfg;
  cfg.enabled = true;
  cfg.pre_seconds = 0.1;
  cfg.post_seconds = 1.0;
  cfg.fps = 10;

  common::VideoRecorder recorder(cfg);
  recorder.TriggerRecording("event1");
  recorder.TriggerRecording("event2");  // Should be ignored
  EXPECT_TRUE(recorder.IsRecording());
}
