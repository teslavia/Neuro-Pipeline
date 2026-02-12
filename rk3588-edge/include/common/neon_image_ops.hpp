#ifndef DATA_PROCESSING_NEON_IMAGE_OPS_HPP_
#define DATA_PROCESSING_NEON_IMAGE_OPS_HPP_

#include <cstddef>
#include <cstdint>
#include <vector>

namespace data_processing {

/**
 * @brief ARM NEON intrinsic image operations (portable fallback).
 *
 * Provides SIMD-accelerated image processing primitives that use
 * ARM NEON intrinsics on aarch64 and scalar fallbacks on other platforms.
 * These operations are common in the V4L2 → RKNN inference pipeline.
 */
class NeonImageOps {
 public:
  /// Convert RGB888 to BGR888 (swap R and B channels).
  /// @param src Source RGB buffer
  /// @param dst Destination BGR buffer (must be same size as src)
  /// @param pixel_count Number of pixels (src/dst must be 3 * pixel_count bytes)
  static void RgbToBgr(const uint8_t* src, uint8_t* dst, size_t pixel_count);

  /// Convert RGBA8888 to RGB888 (strip alpha channel).
  /// @param src Source RGBA buffer (4 * pixel_count bytes)
  /// @param dst Destination RGB buffer (3 * pixel_count bytes)
  /// @param pixel_count Number of pixels
  static void RgbaToRgb(const uint8_t* src, uint8_t* dst, size_t pixel_count);

  /// Apply per-channel mean subtraction and scale (normalization).
  /// out[c] = (in[c] - mean[c]) * scale[c]
  /// @param src Source uint8 image (HWC layout, 3 channels)
  /// @param dst Destination float buffer (3 * pixel_count floats)
  /// @param pixel_count Number of pixels
  /// @param mean Per-channel mean values [R, G, B]
  /// @param scale Per-channel scale values [R, G, B]
  static void NormalizeRgb(const uint8_t* src, float* dst, size_t pixel_count,
                           const float mean[3], const float scale[3]);

  /// Compute absolute difference of two grayscale images.
  /// @param a First image
  /// @param b Second image
  /// @param dst Output |a - b| per pixel
  /// @param size Number of pixels
  static void AbsDiff(const uint8_t* a, const uint8_t* b, uint8_t* dst,
                      size_t size);

  /// Clamp uint8 image to [lo, hi] range.
  static void Clamp(const uint8_t* src, uint8_t* dst, size_t size,
                    uint8_t lo, uint8_t hi);
};

}  // namespace data_processing

#endif  // DATA_PROCESSING_NEON_IMAGE_OPS_HPP_
