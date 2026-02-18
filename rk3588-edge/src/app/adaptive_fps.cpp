#include "neuro/pipeline/adaptive_fps.hpp"

#include <algorithm>

#include "neuro/core/logger.hpp"

namespace neuro::pipeline {

AdaptiveFPSController::AdaptiveFPSController(const Config& config)
    : config_(config), current_fps_(config.idle_fps) {}

void AdaptiveFPSController::Update(int detection_count) {
  if (detection_count > 0) {
    frames_with_detection_++;
    frames_without_detection_ = 0;

    // Ramp up toward active_fps
    if (config_.ramp_up_frames <= 0) {
      current_fps_ = config_.active_fps;
    } else {
      float progress = static_cast<float>(frames_with_detection_) /
                       static_cast<float>(config_.ramp_up_frames);
      progress = std::min(progress, 1.0f);
      current_fps_ = static_cast<uint32_t>(
          config_.idle_fps +
          progress * static_cast<float>(config_.active_fps - config_.idle_fps));
    }
  } else {
    frames_without_detection_++;
    frames_with_detection_ = 0;

    // Ramp down toward idle_fps
    if (config_.ramp_down_frames <= 0) {
      current_fps_ = config_.idle_fps;
    } else {
      float progress = static_cast<float>(frames_without_detection_) /
                       static_cast<float>(config_.ramp_down_frames);
      progress = std::min(progress, 1.0f);
      current_fps_ = static_cast<uint32_t>(
          config_.active_fps -
          progress * static_cast<float>(config_.active_fps - config_.idle_fps));
    }
  }

  // Clamp to [min_fps, max_fps]
  current_fps_ = std::clamp(current_fps_, config_.min_fps, config_.max_fps);
}

uint32_t AdaptiveFPSController::GetTargetFPS() const {
  return current_fps_;
}

uint64_t AdaptiveFPSController::GetFrameDelayUs() const {
  if (current_fps_ == 0) return 0;
  return 1000000ULL / current_fps_;
}

void AdaptiveFPSController::Reset() {
  current_fps_ = config_.idle_fps;
  frames_without_detection_ = 0;
  frames_with_detection_ = 0;
}

}  // namespace app
