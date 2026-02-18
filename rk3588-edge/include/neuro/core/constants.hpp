#ifndef NEURO_CORE_CONSTANTS_HPP_
#define NEURO_CORE_CONSTANTS_HPP_

#include <cstddef>
#include <cstdint>

namespace neuro::core {

// Video / streaming
constexpr size_t kVideoChunkSize = 256 * 1024;       // 256KB read chunk
constexpr size_t kMaxCameras = 8;

// Backoff / reconnection
constexpr int kDefaultBackoffMs = 1000;
constexpr int kMaxBackoffMs = 30000;

// Memory pool
constexpr size_t kDefaultBufferCount = 8;

// Health / FPS reporting intervals
constexpr double kHealthUpdateIntervalSec = 5.0;
constexpr double kFPSUpdateIntervalSec = 1.0;

// Version
constexpr const char* kEdgeVersion = "2.2.2";

}  // namespace neuro::core

#endif  // NEURO_CORE_CONSTANTS_HPP_
