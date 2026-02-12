#include "common/neon_image_ops.hpp"

#include <algorithm>
#include <cmath>

// On ARM64, use NEON intrinsics; elsewhere, scalar fallback
#if defined(__aarch64__) || defined(__ARM_NEON)
#include <arm_neon.h>
#define USE_NEON 1
#else
#define USE_NEON 0
#endif

namespace data_processing {

void NeonImageOps::RgbToBgr(const uint8_t* src, uint8_t* dst,
                             size_t pixel_count) {
  if (!src || !dst || pixel_count == 0) return;

  size_t i = 0;

#if USE_NEON
  // Process 16 pixels at a time using NEON
  for (; i + 16 <= pixel_count; i += 16) {
    uint8x16x3_t rgb = vld3q_u8(src + i * 3);
    // Swap R and B
    uint8x16_t tmp = rgb.val[0];
    rgb.val[0] = rgb.val[2];
    rgb.val[2] = tmp;
    vst3q_u8(dst + i * 3, rgb);
  }
#endif

  // Scalar fallback for remaining pixels
  for (; i < pixel_count; ++i) {
    size_t off = i * 3;
    dst[off + 0] = src[off + 2];  // B ← R
    dst[off + 1] = src[off + 1];  // G ← G
    dst[off + 2] = src[off + 0];  // R ← B
  }
}

void NeonImageOps::RgbaToRgb(const uint8_t* src, uint8_t* dst,
                              size_t pixel_count) {
  if (!src || !dst || pixel_count == 0) return;

  size_t i = 0;

#if USE_NEON
  for (; i + 16 <= pixel_count; i += 16) {
    uint8x16x4_t rgba = vld4q_u8(src + i * 4);
    uint8x16x3_t rgb;
    rgb.val[0] = rgba.val[0];
    rgb.val[1] = rgba.val[1];
    rgb.val[2] = rgba.val[2];
    vst3q_u8(dst + i * 3, rgb);
  }
#endif

  for (; i < pixel_count; ++i) {
    dst[i * 3 + 0] = src[i * 4 + 0];
    dst[i * 3 + 1] = src[i * 4 + 1];
    dst[i * 3 + 2] = src[i * 4 + 2];
  }
}

void NeonImageOps::NormalizeRgb(const uint8_t* src, float* dst,
                                size_t pixel_count, const float mean[3],
                                const float scale[3]) {
  if (!src || !dst || pixel_count == 0) return;

  for (size_t i = 0; i < pixel_count; ++i) {
    for (int c = 0; c < 3; ++c) {
      dst[i * 3 + c] =
          (static_cast<float>(src[i * 3 + c]) - mean[c]) * scale[c];
    }
  }
}

void NeonImageOps::AbsDiff(const uint8_t* a, const uint8_t* b, uint8_t* dst,
                            size_t size) {
  if (!a || !b || !dst || size == 0) return;

  size_t i = 0;

#if USE_NEON
  for (; i + 16 <= size; i += 16) {
    uint8x16_t va = vld1q_u8(a + i);
    uint8x16_t vb = vld1q_u8(b + i);
    uint8x16_t diff = vabdq_u8(va, vb);
    vst1q_u8(dst + i, diff);
  }
#endif

  for (; i < size; ++i) {
    dst[i] = static_cast<uint8_t>(std::abs(static_cast<int>(a[i]) -
                                           static_cast<int>(b[i])));
  }
}

void NeonImageOps::Clamp(const uint8_t* src, uint8_t* dst, size_t size,
                          uint8_t lo, uint8_t hi) {
  if (!src || !dst || size == 0) return;

  size_t i = 0;

#if USE_NEON
  uint8x16_t vlo = vdupq_n_u8(lo);
  uint8x16_t vhi = vdupq_n_u8(hi);
  for (; i + 16 <= size; i += 16) {
    uint8x16_t v = vld1q_u8(src + i);
    v = vmaxq_u8(v, vlo);
    v = vminq_u8(v, vhi);
    vst1q_u8(dst + i, v);
  }
#endif

  for (; i < size; ++i) {
    dst[i] = std::min(std::max(src[i], lo), hi);
  }
}

}  // namespace data_processing
