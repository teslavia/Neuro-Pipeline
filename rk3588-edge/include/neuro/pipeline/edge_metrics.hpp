#ifndef NEURO_PIPELINE_EDGE_METRICS_HPP_
#define NEURO_PIPELINE_EDGE_METRICS_HPP_

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

namespace neuro::pipeline {

/**
 * @brief Lightweight edge-side metrics collector.
 *
 * Thread-safe atomic counters, gauges, and simple histogram
 * for collecting pipeline performance data on the edge device.
 * Metrics are serialized to a map for gRPC transport.
 */
class EdgeMetrics {
 public:
  static EdgeMetrics& Instance();

  // Counters (monotonically increasing)
  void IncrementFramesProcessed(uint64_t n = 1);
  void IncrementDetectionsTotal(uint64_t n = 1);
  void IncrementInferenceErrors(uint64_t n = 1);

  uint64_t GetFramesProcessed() const;
  uint64_t GetDetectionsTotal() const;
  uint64_t GetInferenceErrors() const;

  // Histograms (simple: track count, sum, min, max)
  void RecordInferenceLatencyMs(double ms);
  void RecordRgaLatencyMs(double ms);

  struct HistogramSnapshot {
    uint64_t count = 0;
    double sum = 0.0;
    double min = 0.0;
    double max = 0.0;
    double avg() const { return count > 0 ? sum / count : 0.0; }
  };

  HistogramSnapshot GetInferenceLatency() const;
  HistogramSnapshot GetRgaLatency() const;

  // Gauges (current value)
  void SetFPS(double fps);
  void SetNPUUtilization(double pct);

  double GetFPS() const;
  double GetNPUUtilization() const;

  // Serialize all metrics to key-value map (for gRPC metadata)
  std::vector<std::pair<std::string, std::string>> Snapshot() const;

  // Reset all metrics (for testing)
  void Reset();

 private:
  EdgeMetrics() = default;

  // Counters
  std::atomic<uint64_t> frames_processed_{0};
  std::atomic<uint64_t> detections_total_{0};
  std::atomic<uint64_t> inference_errors_{0};

  // Histogram data (protected by mutex for compound updates)
  mutable std::mutex hist_mu_;
  HistogramSnapshot inference_latency_{};
  HistogramSnapshot rga_latency_{};

  // Gauges
  std::atomic<double> fps_{0.0};
  std::atomic<double> npu_utilization_{0.0};
};

}  // namespace neuro::pipeline

#endif  // NEURO_PIPELINE_EDGE_METRICS_HPP_
