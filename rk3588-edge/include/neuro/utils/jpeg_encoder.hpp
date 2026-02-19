#ifndef NEURO_UTILS_JPEG_ENCODER_HPP_
#define NEURO_UTILS_JPEG_ENCODER_HPP_

#include <cstdint>
#include <string>

// stb_image_write: define implementation in exactly one .cpp
// Here we only include the declarations; the implementation is
// compiled via a dedicated .cpp translation unit.
#include "stb_image_write.h"

namespace neuro::utils {

/// Encode RGB888 raw pixels to JPEG bytes in memory.
/// @param rgb_data  Pointer to width*height*3 bytes (RGB888)
/// @param width     Image width in pixels
/// @param height    Image height in pixels
/// @param quality   JPEG quality 1-100 (default 70)
/// @return JPEG-encoded bytes as std::string (empty on failure)
inline std::string EncodeJPEG(const uint8_t* rgb_data, int width, int height,
                              int quality = 70) {
  std::string output;
  auto write_func = [](void* context, void* data, int size) {
    auto* out = static_cast<std::string*>(context);
    out->append(static_cast<const char*>(data), static_cast<size_t>(size));
  };
  int ok = stbi_write_jpg_to_func(write_func, &output, width, height,
                                   3 /*RGB channels*/, rgb_data, quality);
  if (!ok) output.clear();
  return output;
}

}  // namespace neuro::utils

#endif  // NEURO_UTILS_JPEG_ENCODER_HPP_
