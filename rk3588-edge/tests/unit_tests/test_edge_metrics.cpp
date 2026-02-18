#include <gtest/gtest.h>
#include "neuro/pipeline/edge_metrics.hpp"

class EdgeMetricsTest : public ::testing::Test {
 protected:
  void SetUp() override {
    neuro::pipeline::EdgeMetrics::Instance().Reset();
  }
};

TEST_F(EdgeMetricsTest, CountersStartAtZero) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  EXPECT_EQ(m.GetFramesProcessed(), 0u);
  EXPECT_EQ(m.GetDetectionsTotal(), 0u);
  EXPECT_EQ(m.GetInferenceErrors(), 0u);
}

TEST_F(EdgeMetricsTest, IncrementCounters) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.IncrementFramesProcessed(5);
  m.IncrementDetectionsTotal(3);
  m.IncrementInferenceErrors(1);
  EXPECT_EQ(m.GetFramesProcessed(), 5u);
  EXPECT_EQ(m.GetDetectionsTotal(), 3u);
  EXPECT_EQ(m.GetInferenceErrors(), 1u);
}

TEST_F(EdgeMetricsTest, GaugesDefaultZero) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  EXPECT_DOUBLE_EQ(m.GetFPS(), 0.0);
  EXPECT_DOUBLE_EQ(m.GetNPUUtilization(), 0.0);
}

TEST_F(EdgeMetricsTest, SetGauges) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.SetFPS(29.5);
  m.SetNPUUtilization(72.3);
  EXPECT_DOUBLE_EQ(m.GetFPS(), 29.5);
  EXPECT_DOUBLE_EQ(m.GetNPUUtilization(), 72.3);
}

TEST_F(EdgeMetricsTest, HistogramRecording) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.RecordInferenceLatencyMs(10.0);
  m.RecordInferenceLatencyMs(20.0);
  m.RecordInferenceLatencyMs(30.0);
  auto snap = m.GetInferenceLatency();
  EXPECT_EQ(snap.count, 3u);
  EXPECT_DOUBLE_EQ(snap.sum, 60.0);
  EXPECT_DOUBLE_EQ(snap.min, 10.0);
  EXPECT_DOUBLE_EQ(snap.max, 30.0);
  EXPECT_DOUBLE_EQ(snap.avg(), 20.0);
}

TEST_F(EdgeMetricsTest, RgaHistogram) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.RecordRgaLatencyMs(5.0);
  auto snap = m.GetRgaLatency();
  EXPECT_EQ(snap.count, 1u);
  EXPECT_DOUBLE_EQ(snap.avg(), 5.0);
}

TEST_F(EdgeMetricsTest, SnapshotContainsAllKeys) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.IncrementFramesProcessed(100);
  m.SetFPS(30.0);
  auto snap = m.Snapshot();
  // Should have at least 8 entries
  EXPECT_GE(snap.size(), 8u);
  // Check specific keys exist
  bool found_fps = false;
  bool found_frames = false;
  for (const auto& kv : snap) {
    if (kv.first == "fps") found_fps = true;
    if (kv.first == "frames_processed") found_frames = true;
  }
  EXPECT_TRUE(found_fps);
  EXPECT_TRUE(found_frames);
}

TEST_F(EdgeMetricsTest, ResetClearsAll) {
  auto& m = neuro::pipeline::EdgeMetrics::Instance();
  m.IncrementFramesProcessed(10);
  m.SetFPS(30.0);
  m.RecordInferenceLatencyMs(15.0);
  m.Reset();
  EXPECT_EQ(m.GetFramesProcessed(), 0u);
  EXPECT_DOUBLE_EQ(m.GetFPS(), 0.0);
  EXPECT_EQ(m.GetInferenceLatency().count, 0u);
}
