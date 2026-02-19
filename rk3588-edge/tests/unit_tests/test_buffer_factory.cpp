#include <gtest/gtest.h>

#include "neuro/core/buffer.hpp"

namespace {

class BufferFactoryTest : public ::testing::Test {
 protected:
  static constexpr size_t kTestSize = 4096;
};

TEST_F(BufferFactoryTest, CreateDMABufferReturnsNonNull) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);
}

TEST_F(BufferFactoryTest, CreateDMABufferReturnsCorrectSize) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);
  EXPECT_EQ(buffer->Size(), kTestSize);
}

TEST_F(BufferFactoryTest, CreateDMABufferDataIsAccessible) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);
  void* data = buffer->Data();
  ASSERT_NE(data, nullptr);

  // Should be writable
  auto* bytes = static_cast<uint8_t*>(data);
  bytes[0] = 0x42;
  bytes[kTestSize - 1] = 0x24;
  EXPECT_EQ(bytes[0], 0x42);
  EXPECT_EQ(bytes[kTestSize - 1], 0x24);
}

TEST_F(BufferFactoryTest, CreateDMABufferGetDMABufFd) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);
  // In mock mode, this should return a simulated fd (>= 100)
  // In real mode, this should return a valid fd (>= 0)
  int fd = buffer->GetDMABufFd();
#ifdef USE_MOCK_HAL
  EXPECT_GE(fd, 100);  // DmaBufSim starts at fd 100
#else
  EXPECT_GE(fd, 0);  // Real DRM should give valid fd
#endif
}

TEST_F(BufferFactoryTest, CreateDMABufferMetadataRoundTrip) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);

  neuro::core::Buffer::Metadata meta;
  meta.width = 1920;
  meta.height = 1080;
  meta.stride = 1920;
  meta.format = 0x3231564E;  // NV12
  meta.timestamp_us = 1234567890;
  meta.frame_id = 42;

  buffer->SetMetadata(meta);
  const auto& retrieved = buffer->GetMetadata();

  EXPECT_EQ(retrieved.width, meta.width);
  EXPECT_EQ(retrieved.height, meta.height);
  EXPECT_EQ(retrieved.stride, meta.stride);
  EXPECT_EQ(retrieved.format, meta.format);
  EXPECT_EQ(retrieved.timestamp_us, meta.timestamp_us);
  EXPECT_EQ(retrieved.frame_id, meta.frame_id);
}

TEST_F(BufferFactoryTest, CreateDMABufferSyncForDeviceNoThrow) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  ASSERT_NE(buffer, nullptr);

  // Should not throw in either direction
  EXPECT_NO_THROW(buffer->SyncForDevice(true));   // CPU → DMA
  EXPECT_NO_THROW(buffer->SyncForDevice(false));  // DMA → CPU
}

TEST_F(BufferFactoryTest, CreateMappedBufferReturnsNonNull) {
  std::vector<uint8_t> src_data(kTestSize, 0xAB);
  auto buffer = neuro::core::BufferFactory::CreateMappedBuffer(
      src_data.data(), kTestSize);
  ASSERT_NE(buffer, nullptr);
}

TEST_F(BufferFactoryTest, CreateMappedBufferCopiesData) {
  std::vector<uint8_t> src_data(kTestSize, 0xAB);
  auto buffer = neuro::core::BufferFactory::CreateMappedBuffer(
      src_data.data(), kTestSize);
  ASSERT_NE(buffer, nullptr);

  // Original data should be copied
  auto* buf_data = static_cast<uint8_t*>(buffer->Data());
  EXPECT_EQ(buf_data[0], 0xAB);
  EXPECT_EQ(buf_data[kTestSize - 1], 0xAB);

  // Modifying source should not affect buffer (it's a copy)
  src_data[0] = 0xCD;
  EXPECT_EQ(buf_data[0], 0xAB);
}

TEST_F(BufferFactoryTest, CreateMappedBufferNoDMAFd) {
  std::vector<uint8_t> src_data(kTestSize);
  auto buffer = neuro::core::BufferFactory::CreateMappedBuffer(
      src_data.data(), kTestSize);
  ASSERT_NE(buffer, nullptr);
  // Mapped buffer should not have a DMA fd
  EXPECT_EQ(buffer->GetDMABufFd(), -1);
}

TEST_F(BufferFactoryTest, MultipleDMABuffersAreIndependent) {
  auto buffer1 = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);
  auto buffer2 = neuro::core::BufferFactory::CreateDMABuffer(kTestSize);

  ASSERT_NE(buffer1, nullptr);
  ASSERT_NE(buffer2, nullptr);

  // Should have different virtual addresses
  EXPECT_NE(buffer1->Data(), buffer2->Data());

  // Should have different DMA fds
  EXPECT_NE(buffer1->GetDMABufFd(), buffer2->GetDMABufFd());
}

}  // namespace
