#include <gtest/gtest.h>

#include "neuro/core/buffer.hpp"

namespace {

TEST(ZeroCopyBufferTest, CreateMappedBuffer) {
  uint8_t data[] = {1, 2, 3, 4, 5};
  auto buffer = neuro::core::BufferFactory::CreateMappedBuffer(data, sizeof(data));

  ASSERT_NE(buffer, nullptr);
  EXPECT_EQ(buffer->Size(), sizeof(data));
  EXPECT_NE(buffer->Data(), nullptr);
  EXPECT_EQ(buffer->GetDMABufFd(), -1);  // Heap buffer, no DMA fd
}

TEST(ZeroCopyBufferTest, CreateDMABufferFallsBackToHeap) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(4096);

  ASSERT_NE(buffer, nullptr);
  EXPECT_EQ(buffer->Size(), 4096u);
  EXPECT_NE(buffer->Data(), nullptr);
}

TEST(ZeroCopyBufferTest, BufferDataIsReadWritable) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(256);
  ASSERT_NE(buffer, nullptr);

  auto* ptr = static_cast<uint8_t*>(buffer->Data());
  for (int i = 0; i < 256; ++i) {
    ptr[i] = static_cast<uint8_t>(i);
  }
  for (int i = 0; i < 256; ++i) {
    EXPECT_EQ(ptr[i], static_cast<uint8_t>(i));
  }
}

TEST(ZeroCopyBufferTest, SyncForDeviceNoOp) {
  auto buffer = neuro::core::BufferFactory::CreateDMABuffer(1024);
  ASSERT_NE(buffer, nullptr);
  // Should not throw for heap buffer
  buffer->SyncForDevice(true);
  buffer->SyncForDevice(false);
}

}  // namespace
