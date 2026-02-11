#ifndef COMMON_TYPES_HPP_
#define COMMON_TYPES_HPP_

#include <cstdint>
#include <string>

namespace common {

/// Pixel format enumeration (mirrors V4L2 fourcc).
enum class PixelFormat : uint32_t {
  kNV12 = 0x3231564E,    // NV12 (YUV 4:2:0 semi-planar)
  kRGB888 = 0x33424752,  // RGB888
  kBGR888 = 0x33524742,  // BGR888
  kRGBA8888 = 0x41424752,
  kJPEG = 0x4745504A,
};

/// Detection result for a single object.
struct DetectionBox {
  uint32_t class_id = 0;
  std::string class_name;
  float confidence = 0.0f;
  float x_min = 0.0f;
  float y_min = 0.0f;
  float x_max = 0.0f;
  float y_max = 0.0f;
};

/// System metrics snapshot.
struct SystemMetrics {
  float cpu_usage = 0.0f;
  float npu_usage = 0.0f;
  float memory_used_mb = 0.0f;
  float temperature_c = 0.0f;
  uint32_t fps = 0;
};

}  // namespace common

#endif  // COMMON_TYPES_HPP_
