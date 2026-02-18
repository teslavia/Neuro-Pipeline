#include <gtest/gtest.h>

#include "neuro/core/memory_pool.hpp"

namespace {

class MemoryPoolTest : public ::testing::Test {
 protected:
  static constexpr size_t kBlockSize = 1024;
  static constexpr size_t kBlockCount = 10;
};

TEST_F(MemoryPoolTest, InitialStateHasFullCapacity) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  EXPECT_EQ(pool.Available(), kBlockCount);
  EXPECT_EQ(pool.Capacity(), kBlockCount);
  EXPECT_EQ(pool.BlockSize(), kBlockSize);
}

TEST_F(MemoryPoolTest, AllocateReducesAvailable) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);
  EXPECT_EQ(pool.Available(), kBlockCount - 1);
}

TEST_F(MemoryPoolTest, FreeRestoresAvailable) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);
  pool.Free(ptr);
  EXPECT_EQ(pool.Available(), kBlockCount);
}

TEST_F(MemoryPoolTest, ExhaustPoolReturnsNull) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  for (size_t i = 0; i < kBlockCount; ++i) {
    ASSERT_NE(pool.Allocate(), nullptr);
  }
  EXPECT_EQ(pool.Allocate(), nullptr);
  EXPECT_EQ(pool.Available(), 0u);
}

TEST_F(MemoryPoolTest, AllocatedBlocksAreWritable) {
  neuro::core::MemoryPool pool(kBlockSize, 1);
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
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  int dummy = 0;
  EXPECT_THROW(pool.Free(&dummy), std::invalid_argument);
}

TEST_F(MemoryPoolTest, FreeNullptrIsNoOp) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  pool.Free(nullptr);  // Should not throw
  EXPECT_EQ(pool.Available(), kBlockCount);
}

// ---- Physical / Virtual Address Simulation Tests ----

TEST_F(MemoryPoolTest, PhysBaseAddrDefault) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  EXPECT_EQ(pool.PhysBaseAddr(), 0x10000000u);
  EXPECT_EQ(pool.PhysEndAddr(), 0x10000000u + kBlockSize * kBlockCount);
}

TEST_F(MemoryPoolTest, PhysBaseAddrCustom) {
  constexpr uint64_t kCustomBase = 0x80000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kCustomBase);
  EXPECT_EQ(pool.PhysBaseAddr(), kCustomBase);
  EXPECT_EQ(pool.PhysEndAddr(), kCustomBase + kBlockSize * kBlockCount);
}

TEST_F(MemoryPoolTest, ContainsVirtForAllocatedBlock) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);

  EXPECT_TRUE(pool.ContainsVirt(ptr));

  // Interior pointer within the block should also be contained
  auto* interior = static_cast<uint8_t*>(ptr) + kBlockSize / 2;
  EXPECT_TRUE(pool.ContainsVirt(interior));

  pool.Free(ptr);
}

TEST_F(MemoryPoolTest, ContainsVirtRejectsForeignPointer) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  int dummy = 0;
  EXPECT_FALSE(pool.ContainsVirt(&dummy));
  EXPECT_FALSE(pool.ContainsVirt(nullptr));
}

TEST_F(MemoryPoolTest, ContainsPhysInsideRange) {
  constexpr uint64_t kBase = 0x10000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  EXPECT_TRUE(pool.ContainsPhys(kBase));
  EXPECT_TRUE(pool.ContainsPhys(kBase + 1));
  EXPECT_TRUE(pool.ContainsPhys(kBase + kBlockSize * kBlockCount - 1));
}

TEST_F(MemoryPoolTest, ContainsPhysRejectsOutside) {
  constexpr uint64_t kBase = 0x10000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  EXPECT_FALSE(pool.ContainsPhys(kBase - 1));
  EXPECT_FALSE(pool.ContainsPhys(kBase + kBlockSize * kBlockCount));
  EXPECT_FALSE(pool.ContainsPhys(0));
}

TEST_F(MemoryPoolTest, VirtToPhysRoundTrip) {
  constexpr uint64_t kBase = 0x20000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);

  uint64_t phys = pool.VirtToPhys(ptr);
  EXPECT_GE(phys, kBase);
  EXPECT_LT(phys, pool.PhysEndAddr());

  // Round-trip: PhysToVirt should return the original pointer
  void* virt_back = pool.PhysToVirt(phys);
  EXPECT_EQ(virt_back, ptr);

  pool.Free(ptr);
}

TEST_F(MemoryPoolTest, VirtToPhysConsecutiveBlocks) {
  constexpr uint64_t kBase = 0x10000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  // Allocate all blocks and verify their physical addresses are within range
  std::vector<void*> ptrs;
  for (size_t i = 0; i < kBlockCount; ++i) {
    void* p = pool.Allocate();
    ASSERT_NE(p, nullptr);
    ptrs.push_back(p);

    uint64_t phys = pool.VirtToPhys(p);
    EXPECT_GE(phys, kBase);
    EXPECT_LT(phys, pool.PhysEndAddr());
    // Physical address must be block-aligned relative to base
    EXPECT_EQ((phys - kBase) % kBlockSize, 0u);
  }

  for (auto* p : ptrs) {
    pool.Free(p);
  }
}

TEST_F(MemoryPoolTest, VirtToPhysInvalidReturnsZero) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  int dummy = 0;
  EXPECT_EQ(pool.VirtToPhys(&dummy), 0u);
  EXPECT_EQ(pool.VirtToPhys(nullptr), 0u);
}

TEST_F(MemoryPoolTest, PhysToVirtInvalidReturnsNull) {
  constexpr uint64_t kBase = 0x10000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  EXPECT_EQ(pool.PhysToVirt(0), nullptr);
  EXPECT_EQ(pool.PhysToVirt(kBase - 1), nullptr);
  EXPECT_EQ(pool.PhysToVirt(pool.PhysEndAddr()), nullptr);
}

TEST_F(MemoryPoolTest, PhysToVirtInteriorOffset) {
  constexpr uint64_t kBase = 0x10000000;
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, kBase);

  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);

  uint64_t phys = pool.VirtToPhys(ptr);
  // Access an interior offset within the block
  constexpr size_t kOffset = 128;
  void* interior_virt = pool.PhysToVirt(phys + kOffset);
  ASSERT_NE(interior_virt, nullptr);
  EXPECT_EQ(interior_virt, static_cast<uint8_t*>(ptr) + kOffset);

  pool.Free(ptr);
}

TEST_F(MemoryPoolTest, WriteViaVirtReadViaPhys) {
  constexpr uint64_t kBase = 0x30000000;
  neuro::core::MemoryPool pool(kBlockSize, 1, kBase);

  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);

  // Write data via virtual address
  auto* virt_data = static_cast<uint8_t*>(ptr);
  for (size_t i = 0; i < 16; ++i) {
    virt_data[i] = static_cast<uint8_t>(0xA0 + i);
  }

  // Read back via physical address translation
  uint64_t phys = pool.VirtToPhys(ptr);
  auto* phys_data = static_cast<uint8_t*>(pool.PhysToVirt(phys));
  ASSERT_NE(phys_data, nullptr);

  for (size_t i = 0; i < 16; ++i) {
    EXPECT_EQ(phys_data[i], static_cast<uint8_t>(0xA0 + i));
  }

  pool.Free(ptr);
}

// ---- Stats Tests ----

TEST_F(MemoryPoolTest, StatsTrackAllocationsAndFrees) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  void* p1 = pool.Allocate();
  void* p2 = pool.Allocate();
  pool.Free(p1);

  auto stats = pool.GetStats();
  EXPECT_EQ(stats.total_allocations, 2u);
  EXPECT_EQ(stats.total_frees, 1u);
  EXPECT_EQ(stats.peak_usage, 2u);

  pool.Free(p2);
}

TEST_F(MemoryPoolTest, StatsPeakUsage) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount);
  std::vector<void*> ptrs;
  for (size_t i = 0; i < 5; ++i) {
    ptrs.push_back(pool.Allocate());
  }
  for (auto* p : ptrs) pool.Free(p);

  // Allocate 2 more
  pool.Allocate();
  pool.Allocate();

  auto stats = pool.GetStats();
  EXPECT_EQ(stats.peak_usage, 5u);  // Peak was 5
}

TEST_F(MemoryPoolTest, AlignmentParameter) {
  neuro::core::MemoryPool pool(kBlockSize, kBlockCount, 0x10000000, 64);
  EXPECT_EQ(pool.Alignment(), 64u);
  void* ptr = pool.Allocate();
  ASSERT_NE(ptr, nullptr);
  pool.Free(ptr);
}

}  // namespace
