#include "common/edge_metrics.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace common {

EdgeMetrics& EdgeMetrics::Instance() {
  static EdgeMetrics instance;
  return instance;
}

void EdgeMetrics::IncrementFramesProcessed(uint64_t n) {
  frames_processed_.fetch_add(n, std::memory_order_relaxed);
}

void EdgeMetrics::IncrementDetectionsTotal(uint64_t n) {
  detections_total_.fetch_add(n, std::memory_order_relaxed);
}

void EdgeMetrics::IncrementInferenceErrors(uint64_t n) {
  inference_errors_.fetch_add(n, std::memory_order_relaxed);
}

uint64_t EdgeMetrics::GetFramesProcessed() const {
  return frames_processed_.load(std::memory_order_relaxed);
}

uint64_t EdgeMetrics::GetDetectionsTotal() const {
  return detections_total_.load(std::memory_order_relaxed);
}

uint64_t EdgeMetrics::GetInferenceErrors() const {
  return inference_errors_.load(std::memory_order_relaxed);
}

void EdgeMetrics::RecordInferenceLatencyMs(double ms) {
  std::lock_guard<std::mutex> lock(hist_mu_);
  if (inference_latency_.count == 0) {
    inference_latency_.min = ms;
    inference_latency_.max = ms;
  } else {
    inference_latency_.min = std::min(inference_latency_.min, ms);
    inference_latency_.max = std::max(inference_latency_.max, ms);
  }
  inference_latency_.sum += ms;
  inference_latency_.count++;
}

void EdgeMetrics::RecordRgaLatencyMs(double ms) {
  std::lock_guard<std::mutex> lock(hist_mu_);
  if (rga_latency_.count == 0) {
    rga_latency_.min = ms;
    rga_latency_.max = ms;
  } else {
    rga_latency_.min = std::min(rga_latency_.min, ms);
    rga_latency_.max = std::max(rga_latency_.max, ms);
  }
  rga_latency_.sum += ms;
  rga_latency_.count++;
}

EdgeMetrics::HistogramSnapshot EdgeMetrics::GetInferenceLatency() const {
  std::lock_guard<std::mutex> lock(hist_mu_);
  return inference_latency_;
}

EdgeMetrics::HistogramSnapshot EdgeMetrics::GetRgaLatency() const {
  std::lock_guard<std::mutex> lock(hist_mu_);
  return rga_latency_;
}

void EdgeMetrics::SetFPS(double fps) {
  fps_.store(fps, std::memory_order_relaxed);
}

void EdgeMetrics::SetNPUUtilization(double pct) {
  npu_utilization_.store(pct, std::memory_order_relaxed);
}

double EdgeMetrics::GetFPS() const {
  return fps_.load(std::memory_order_relaxed);
}

double EdgeMetrics::GetNPUUtilization() const {
  return npu_utilization_.load(std::memory_order_relaxed);
}

std::vector<std::pair<std::string, std::string>> EdgeMetrics::Snapshot() const {
  std::vector<std::pair<std::string, std::string>> out;
  auto to_str = [](auto v) {
    std::ostringstream ss;
    ss << v;
    return ss.str();
  };
  out.emplace_back("frames_processed", to_str(GetFramesProcessed()));
  out.emplace_back("detections_total", to_str(GetDetectionsTotal()));
  out.emplace_back("inference_errors", to_str(GetInferenceErrors()));
  out.emplace_back("fps", to_str(GetFPS()));
  out.emplace_back("npu_utilization", to_str(GetNPUUtilization()));
  auto inf_lat = GetInferenceLatency();
  out.emplace_back("inference_latency_avg_ms", to_str(inf_lat.avg()));
  out.emplace_back("inference_latency_count", to_str(inf_lat.count));
  auto rga_lat = GetRgaLatency();
  out.emplace_back("rga_latency_avg_ms", to_str(rga_lat.avg()));
  return out;
}

void EdgeMetrics::Reset() {
  frames_processed_ = 0;
  detections_total_ = 0;
  inference_errors_ = 0;
  fps_ = 0.0;
  npu_utilization_ = 0.0;
  std::lock_guard<std::mutex> lock(hist_mu_);
  inference_latency_ = {};
  rga_latency_ = {};
}

}  // namespace common