#ifndef NEURO_HAL_INPUT_SOURCE_HPP_
#define NEURO_HAL_INPUT_SOURCE_HPP_

#include <cstdint>
#include <memory>

#include "neuro/core/buffer.hpp"

namespace neuro::hal {

/**
 * @brief Abstract input source — Strategy interface for frame acquisition.
 *
 * Unifies V4L2Camera, RTSPSource, and video-file decoding behind a single
 * polymorphic API so PipelineCoordinator no longer branches on source type.
 */
class InputSource {
 public:
  virtual ~InputSource() = default;

  /// One-time hardware / resource setup.
  virtual bool Initialize() = 0;

  /// Begin producing frames (e.g. V4L2 STREAMON, RTSP PLAY).
  virtual bool Start() = 0;

  /// Stop producing frames.
  virtual void Stop() = 0;

  /// Grab the next frame (blocking). Returns nullptr on EOS / error.
  virtual std::shared_ptr<core::Buffer> CaptureFrame() = 0;

  /// Return a frame to the source's buffer pool.
  virtual void ReleaseFrame(std::shared_ptr<core::Buffer> frame) = 0;

  /// Source dimensions (after decode / before RGA resize).
  virtual uint32_t Width() const = 0;
  virtual uint32_t Height() const = 0;
};

}  // namespace neuro::hal

#endif  // NEURO_HAL_INPUT_SOURCE_HPP_
