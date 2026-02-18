#include <gtest/gtest.h>

#include <algorithm>
#include <cstring>
#include <vector>

#include "neuro/pipeline/neon_image_ops.hpp"

namespace {

using neuro::pipeline::NeonImageOps;

// ---- RgbToBgr ----

TEST(NeonImageOpsTest, RgbToBgrSwapsChannels) {
  // 2 pixels: (R=10, G=20, B=30), (R=40, G=50, B=60)
  uint8_t src[] = {10, 20, 30, 40, 50, 60};
  uint8_t dst[6] = {};

  NeonImageOps::RgbToBgr(src, dst, 2);

  // Expected BGR: (30, 20, 10), (60, 50, 40)
  EXPECT_EQ(dst[0], 30);
  EXPECT_EQ(dst[1], 20);
  EXPECT_EQ(dst[2], 10);
  EXPECT_EQ(dst[3], 60);
  EXPECT_EQ(dst[4], 50);
  EXPECT_EQ(dst[5], 40);
}

TEST(NeonImageOpsTest, RgbToBgrRoundTrip) {
  uint8_t original[] = {100, 150, 200};
  uint8_t intermediate[3] = {};
  uint8_t result[3] = {};

  NeonImageOps::RgbToBgr(original, intermediate, 1);
  NeonImageOps::RgbToBgr(intermediate, result, 1);

  EXPECT_EQ(result[0], original[0]);
  EXPECT_EQ(result[1], original[1]);
  EXPECT_EQ(result[2], original[2]);
}

TEST(NeonImageOpsTest, RgbToBgrLargeBuffer) {
  constexpr size_t kPixels = 256;  // Test beyond NEON batch size (16)
  std::vector<uint8_t> src(kPixels * 3);
  std::vector<uint8_t> dst(kPixels * 3, 0);

  for (size_t i = 0; i < kPixels; ++i) {
    src[i * 3 + 0] = static_cast<uint8_t>(i);        // R
    src[i * 3 + 1] = static_cast<uint8_t>(i + 1);    // G
    src[i * 3 + 2] = static_cast<uint8_t>(i + 2);    // B
  }

  NeonImageOps::RgbToBgr(src.data(), dst.data(), kPixels);

  for (size_t i = 0; i < kPixels; ++i) {
    EXPECT_EQ(dst[i * 3 + 0], src[i * 3 + 2]) << "pixel " << i << " B";
    EXPECT_EQ(dst[i * 3 + 1], src[i * 3 + 1]) << "pixel " << i << " G";
    EXPECT_EQ(dst[i * 3 + 2], src[i * 3 + 0]) << "pixel " << i << " R";
  }
}

TEST(NeonImageOpsTest, RgbToBgrNullSafe) {
  uint8_t buf[3] = {};
  NeonImageOps::RgbToBgr(nullptr, buf, 1);    // No crash
  NeonImageOps::RgbToBgr(buf, nullptr, 1);    // No crash
  NeonImageOps::RgbToBgr(buf, buf, 0);        // No crash
}

// ---- RgbaToRgb ----

TEST(NeonImageOpsTest, RgbaToRgbStripsAlpha) {
  uint8_t src[] = {10, 20, 30, 255, 40, 50, 60, 128};
  uint8_t dst[6] = {};

  NeonImageOps::RgbaToRgb(src, dst, 2);

  EXPECT_EQ(dst[0], 10);
  EXPECT_EQ(dst[1], 20);
  EXPECT_EQ(dst[2], 30);
  EXPECT_EQ(dst[3], 40);
  EXPECT_EQ(dst[4], 50);
  EXPECT_EQ(dst[5], 60);
}

TEST(NeonImageOpsTest, RgbaToRgbLargeBuffer) {
  constexpr size_t kPixels = 100;
  std::vector<uint8_t> src(kPixels * 4);
  std::vector<uint8_t> dst(kPixels * 3, 0);

  for (size_t i = 0; i < kPixels; ++i) {
    src[i * 4 + 0] = static_cast<uint8_t>(i);
    src[i * 4 + 1] = static_cast<uint8_t>(i + 10);
    src[i * 4 + 2] = static_cast<uint8_t>(i + 20);
    src[i * 4 + 3] = 0xFF;  // alpha
  }

  NeonImageOps::RgbaToRgb(src.data(), dst.data(), kPixels);

  for (size_t i = 0; i < kPixels; ++i) {
    EXPECT_EQ(dst[i * 3 + 0], src[i * 4 + 0]);
    EXPECT_EQ(dst[i * 3 + 1], src[i * 4 + 1]);
    EXPECT_EQ(dst[i * 3 + 2], src[i * 4 + 2]);
  }
}

// ---- NormalizeRgb ----

TEST(NeonImageOpsTest, NormalizeRgbZeroMeanUnitScale) {
  uint8_t src[] = {100, 150, 200};
  float dst[3] = {};
  float mean[3] = {0.0f, 0.0f, 0.0f};
  float scale[3] = {1.0f, 1.0f, 1.0f};

  NeonImageOps::NormalizeRgb(src, dst, 1, mean, scale);

  EXPECT_FLOAT_EQ(dst[0], 100.0f);
  EXPECT_FLOAT_EQ(dst[1], 150.0f);
  EXPECT_FLOAT_EQ(dst[2], 200.0f);
}

TEST(NeonImageOpsTest, NormalizeRgbImageNetStyle) {
  // ImageNet normalization: mean=[123.675, 116.28, 103.53], scale=[1/58.395, 1/57.12, 1/57.375]
  uint8_t src[] = {124, 116, 104};
  float dst[3] = {};
  float mean[3] = {123.675f, 116.28f, 103.53f};
  float scale[3] = {1.0f / 58.395f, 1.0f / 57.12f, 1.0f / 57.375f};

  NeonImageOps::NormalizeRgb(src, dst, 1, mean, scale);

  // Values should be close to 0 since input ≈ mean
  EXPECT_NEAR(dst[0], 0.0f, 0.02f);
  EXPECT_NEAR(dst[1], 0.0f, 0.02f);
  EXPECT_NEAR(dst[2], 0.0f, 0.02f);
}

// ---- AbsDiff ----

TEST(NeonImageOpsTest, AbsDiffCorrectness) {
  uint8_t a[] = {10, 200, 50, 0};
  uint8_t b[] = {20, 100, 50, 255};
  uint8_t dst[4] = {};

  NeonImageOps::AbsDiff(a, b, dst, 4);

  EXPECT_EQ(dst[0], 10);
  EXPECT_EQ(dst[1], 100);
  EXPECT_EQ(dst[2], 0);
  EXPECT_EQ(dst[3], 255);
}

TEST(NeonImageOpsTest, AbsDiffSymmetric) {
  uint8_t a[] = {30, 80};
  uint8_t b[] = {80, 30};
  uint8_t dst1[2] = {}, dst2[2] = {};

  NeonImageOps::AbsDiff(a, b, dst1, 2);
  NeonImageOps::AbsDiff(b, a, dst2, 2);

  EXPECT_EQ(dst1[0], dst2[0]);
  EXPECT_EQ(dst1[1], dst2[1]);
}

// ---- Clamp ----

TEST(NeonImageOpsTest, ClampWithinRange) {
  uint8_t src[] = {0, 50, 100, 150, 200, 255};
  uint8_t dst[6] = {};

  NeonImageOps::Clamp(src, dst, 6, 30, 180);

  EXPECT_EQ(dst[0], 30);    // clamped up
  EXPECT_EQ(dst[1], 50);    // within range
  EXPECT_EQ(dst[2], 100);   // within range
  EXPECT_EQ(dst[3], 150);   // within range
  EXPECT_EQ(dst[4], 180);   // clamped down
  EXPECT_EQ(dst[5], 180);   // clamped down
}

TEST(NeonImageOpsTest, ClampFullRange) {
  uint8_t src[] = {0, 128, 255};
  uint8_t dst[3] = {};

  NeonImageOps::Clamp(src, dst, 3, 0, 255);

  EXPECT_EQ(dst[0], 0);
  EXPECT_EQ(dst[1], 128);
  EXPECT_EQ(dst[2], 255);
}

}  // namespace
