#include <gtest/gtest.h>
#include <vector>
#include "neuro/hal/input_source.hpp"
#include "neuro/hal/input_source_factory.hpp"

using namespace neuro::hal;

// ── Concrete Buffer stub (Buffer is abstract) ───────────────

namespace {

class FakeBuffer final : public neuro::core::Buffer {
 public:
  explicit FakeBuffer(size_t sz) : data_(sz, 0) {}
  void* Data() override { return data_.data(); }
  size_t Size() const override { return data_.size(); }
  int GetDMABufFd() const override { return -1; }
  const Metadata& GetMetadata() const override { return meta_; }
  void SetMetadata(const Metadata& m) override { meta_ = m; }
  void SyncForDevice(bool) override {}
 private:
  std::vector<uint8_t> data_;
  Metadata meta_{};
};

}  // namespace

// ── Interface contract tests via a trivial mock ─────────────

namespace {

class FakeInputSource final : public InputSource {
 public:
  bool Initialize() override { initialized_ = true; return true; }
  bool Start() override      { started_ = true; return initialized_; }
  void Stop() override       { started_ = false; }

  std::shared_ptr<neuro::core::Buffer> CaptureFrame() override {
    if (!started_) return nullptr;
    ++frames_;
    return std::make_shared<FakeBuffer>(320 * 240 * 3);
  }

  void ReleaseFrame(std::shared_ptr<neuro::core::Buffer>) override {
    ++released_;
  }

  uint32_t Width() const override  { return 320; }
  uint32_t Height() const override { return 240; }

  bool initialized_ = false;
  bool started_ = false;
  int frames_ = 0;
  int released_ = 0;
};

}  // namespace

TEST(InputSourceTest, InterfaceLifecycle) {
  FakeInputSource src;
  EXPECT_FALSE(src.initialized_);
  EXPECT_TRUE(src.Initialize());
  EXPECT_TRUE(src.initialized_);

  EXPECT_TRUE(src.Start());
  auto frame = src.CaptureFrame();
  EXPECT_TRUE(frame != nullptr);
  EXPECT_EQ(src.frames_, 1);

  src.ReleaseFrame(frame);
  EXPECT_EQ(src.released_, 1);

  src.Stop();
  EXPECT_TRUE(src.CaptureFrame() == nullptr);
}

TEST(InputSourceTest, Dimensions) {
  FakeInputSource src;
  EXPECT_EQ(src.Width(), 320u);
  EXPECT_EQ(src.Height(), 240u);
}

TEST(InputSourceTest, CaptureWithoutStart) {
  FakeInputSource src;
  src.Initialize();
  // Not started — should return nullptr
  EXPECT_TRUE(src.CaptureFrame() == nullptr);
}

TEST(InputSourceTest, MultipleFrames) {
  FakeInputSource src;
  src.Initialize();
  src.Start();
  for (int i = 0; i < 10; ++i) {
    auto f = src.CaptureFrame();
    EXPECT_TRUE(f != nullptr);
    src.ReleaseFrame(f);
  }
  EXPECT_EQ(src.frames_, 10);
  EXPECT_EQ(src.released_, 10);
}

// ── Factory tests (mock HAL only) ───────────────────────────

#ifdef USE_MOCK_HAL

TEST(InputSourceFactoryTest, CreatesV4L2ForEmptyVideoSource) {
  auto src = InputSourceFactory::Create("", "/dev/video0", 640, 480, 30);
  EXPECT_TRUE(src != nullptr);
  EXPECT_EQ(src->Width(), 640u);
  EXPECT_EQ(src->Height(), 480u);
}

TEST(InputSourceFactoryTest, CreatesRTSPForRtspUrl) {
  auto src = InputSourceFactory::Create(
      "rtsp://192.168.1.100:8554/stream", "", 1920, 1080, 25);
  EXPECT_TRUE(src != nullptr);
  EXPECT_EQ(src->Width(), 1920u);
  EXPECT_EQ(src->Height(), 1080u);
}

TEST(InputSourceFactoryTest, CreatesVideoFileForPath) {
  auto src = InputSourceFactory::Create(
      "/tmp/test.h264", "", 640, 480, 30);
  EXPECT_TRUE(src != nullptr);
  EXPECT_EQ(src->Width(), 640u);
  EXPECT_EQ(src->Height(), 480u);
}

#endif  // USE_MOCK_HAL
