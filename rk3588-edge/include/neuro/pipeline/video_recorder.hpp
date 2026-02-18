#ifndef NEURO_PIPELINE_VIDEO_RECORDER_HPP_
#define NEURO_PIPELINE_VIDEO_RECORDER_HPP_

#include <atomic>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "neuro/core/buffer.hpp"

namespace neuro::pipeline {

/**
 * @brief Event-triggered video recorder with ring buffer.
 *
 * Maintains a ring buffer of recent frames. When triggered,
 * dumps the buffer (pre-event) and continues recording (post-event).
 */
class VideoRecorder {
 public:
  struct Config {
    bool enabled = false;
    double pre_seconds = 10.0;     // Seconds of pre-event buffer
    double post_seconds = 30.0;    // Seconds of post-event recording
    std::string output_dir = "/opt/neuro-pipeline/recordings";
    uint32_t fps = 30;
  };

  explicit VideoRecorder(const Config& config);
  ~VideoRecorder();

  VideoRecorder(const VideoRecorder&) = delete;
  VideoRecorder& operator=(const VideoRecorder&) = delete;

  /// Push a frame into the ring buffer.
  void PushFrame(std::shared_ptr<core::Buffer> frame);

  /// Trigger recording with an event name.
  void TriggerRecording(const std::string& event_name);

  /// Check if currently recording.
  bool IsRecording() const { return recording_.load(); }

  /// Get number of frames in the ring buffer.
  size_t BufferSize() const;

  /// Get total recordings completed.
  uint64_t RecordingsCompleted() const { return recordings_completed_; }

 private:
  Config config_;
  size_t max_buffer_frames_;
  std::deque<std::shared_ptr<core::Buffer>> ring_buffer_;
  mutable std::mutex mu_;
  std::atomic<bool> recording_{false};
  uint64_t recordings_completed_ = 0;
  uint64_t post_frames_remaining_ = 0;
};

}  // namespace neuro::pipeline

#endif  // NEURO_PIPELINE_VIDEO_RECORDER_HPP_
