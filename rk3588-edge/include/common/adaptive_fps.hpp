#ifndef APP_ADAPTIVE_FPS_HPP_
#define APP_ADAPTIVE_FPS_HPP_

#include <cstdint>

namespace app {

class AdaptiveFPSController {
 public:
  struct Config {
    uint32_t min_fps = 5;
    uint32_t max_fps = 30;
    uint32_t idle_fps = 10;       // FPS when no detections
    uint32_t active_fps = 30;     // FPS when detections present
    int ramp_up_frames = 1;       // frames to reach active_fps
    int ramp_down_frames = 90;    // frames (~3s) to reach idle_fps
  };

  explicit AdaptiveFPSController(const Config& config = {});

  /// Call after each frame with detection count.
  void Update(int detection_count);

  /// Get current target FPS.
  uint32_t GetTargetFPS() const;

  /// Get frame delay in microseconds for current FPS.
  uint64_t GetFrameDelayUs() const;

  /// Reset to default state.
  void Reset();

 private:
  Config config_;
  uint32_t current_fps_;
  int frames_without_detection_ = 0;
  int frames_with_detection_ = 0;
};

}  // namespace app

#endif  // APP_ADAPTIVE_FPS_HPP_
