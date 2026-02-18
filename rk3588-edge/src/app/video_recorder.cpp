#include "neuro/pipeline/video_recorder.hpp"

#include <algorithm>
#include <iostream>

namespace neuro::pipeline {

VideoRecorder::VideoRecorder(const Config& config)
    : config_(config),
      max_buffer_frames_(static_cast<size_t>(config.pre_seconds * config.fps)) {
}

VideoRecorder::~VideoRecorder() = default;

void VideoRecorder::PushFrame(std::shared_ptr<core::Buffer> frame) {
  std::lock_guard<std::mutex> lock(mu_);

  if (recording_.load()) {
    // During post-event recording, count down
    if (post_frames_remaining_ > 0) {
      post_frames_remaining_--;
    } else {
      recording_ = false;
      recordings_completed_++;
      std::cout << "[Recorder] Recording complete (#"
                << recordings_completed_ << ")" << std::endl;
    }
  }

  // Always maintain ring buffer
  ring_buffer_.push_back(std::move(frame));
  while (ring_buffer_.size() > max_buffer_frames_) {
    ring_buffer_.pop_front();
  }
}

void VideoRecorder::TriggerRecording(const std::string& event_name) {
  std::lock_guard<std::mutex> lock(mu_);
  if (recording_.load()) return;  // Already recording

  recording_ = true;
  post_frames_remaining_ =
      static_cast<uint64_t>(config_.post_seconds * config_.fps);

  std::cout << "[Recorder] Triggered by '" << event_name
            << "', buffer=" << ring_buffer_.size()
            << " frames, will record " << post_frames_remaining_
            << " more" << std::endl;

  // In real implementation: dump ring_buffer_ to file + continue recording
  // Mock: just track state
}

size_t VideoRecorder::BufferSize() const {
  std::lock_guard<std::mutex> lock(mu_);
  return ring_buffer_.size();
}

}  // namespace common
