#include <gtest/gtest.h>

#include "common/memory_pool.hpp"

namespace {

class MemoryPoolTest : public ::testing::Test {
 protected:
  static constexpr size_t kBlockSize = 1024;
  static constexpr size_t kBlockCount = 10;
};

TEST_F(MemoryPoolTest, InitialStateHasFullCapacity) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  EXPECT_EQ(pool.Available(), kBlockCount);
  EXPECT_EQ(pool.Capacity(), kBlockCount);
  EXPECT_EQ(pool.BlockSize(), kBlockSize);
}

TEST_F(MemoryPoolTest, AllocateReducesAvailable) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);
  EXPECT_EQ(pool.Available(), kBlockCount - 1);
}

TEST_F(MemoryPoolTest, FreeRestoresAvailable) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);
  pool.Free(ptr);
  EXPECT_EQ(pool.Available(), kBlockCount);
}

TEST_F(MemoryPoolTest, ExhaustPoolReturnsNull) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  for (size_t i = 0; i < kBlockCount; ++i) {
    ASSERT_NE(pool.Allocate(), nullptr);
  }
  EXPECT_EQ(pool.Allocate(), nullptr);
  EXPECT_EQ(pool.Available(), 0u);
}

TEST_F(MemoryPoolTest, AllocatedBlocksAreWritable) {
  data_processing::MemoryPool pool(kBlockSize, 1);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);

  // Write and read back
  auto* data = static_cast<uint8_t*>(ptr);
  for (size_t i = 0; i < kBlockSize; ++i) {
    data[i] = static_cast<uint8_t>(i & 0xFF);
  }
  for (size_t i = 0; i < kBlockSize; ++i) {
    EXPECT_EQ(data[i], static_cast<uint8_t>(i & 0xFF));
  }

  pool.Free(ptr);
}

TEST_F(MemoryPoolTest, FreeInvalidPointerThrows) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  int dummy = 0;
  EXPECT_THROW(pool.Free(&dummy), std::invalid_argument);
}

TEST_F(MemoryPoolTest, FreeNullptrIsNoOp) {
  data_processing::MemoryPool pool(kBlockSize, kBlockCount);
  pool.Free(nullptr);  // Should not throw
  EXPECT_EQ(pool.Available(), kBlockCount);
}

}  // namespace
