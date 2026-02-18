#include <gtest/gtest.h>

#include <cstring>

#include "neuro/hal/dmabuf_sim.hpp"

namespace {

using neuro::hal::DmaBufSim;

// ---- Allocation ----

TEST(DmaBufSimTest, AllocateReturnsValidFd) {
  DmaBufSim sim;
  int fd = sim.Allocate(4096);
  EXPECT_GE(fd, 0);
  EXPECT_EQ(sim.AllocatedCount(), 1u);
  EXPECT_EQ(sim.AllocatedBytes(), 4096u);
}

TEST(DmaBufSimTest, AllocateZeroSizeFails) {
  DmaBufSim sim;
  EXPECT_EQ(sim.Allocate(0), -1);
  EXPECT_EQ(sim.AllocatedCount(), 0u);
}

TEST(DmaBufSimTest, MultipleAllocationsGetUniqueFds) {
  DmaBufSim sim;
  int fd1 = sim.Allocate(1024);
  int fd2 = sim.Allocate(2048);
  int fd3 = sim.Allocate(512);

  EXPECT_NE(fd1, fd2);
  EXPECT_NE(fd2, fd3);
  EXPECT_NE(fd1, fd3);
  EXPECT_EQ(sim.AllocatedCount(), 3u);
  EXPECT_EQ(sim.AllocatedBytes(), 1024u + 2048u + 512u);
}

// ---- Free ----

TEST(DmaBufSimTest, FreeReducesCount) {
  DmaBufSim sim;
  int fd = sim.Allocate(4096);
  EXPECT_EQ(sim.AllocatedCount(), 1u);

  sim.Free(fd);
  EXPECT_EQ(sim.AllocatedCount(), 0u);
  EXPECT_EQ(sim.AllocatedBytes(), 0u);
}

TEST(DmaBufSimTest, FreeInvalidFdIsNoOp) {
  DmaBufSim sim;
  sim.Free(999);  // Should not crash
  EXPECT_EQ(sim.AllocatedCount(), 0u);
}

// ---- Mmap ----

TEST(DmaBufSimTest, MmapReturnsWritablePointer) {
  DmaBufSim sim;
  int fd = sim.Allocate(256);

  void* ptr = sim.Mmap(fd);
  ASSERT_NE(ptr, nullptr);

  // Write and verify
  std::memset(ptr, 0xAB, 256);
  auto* bytes = static_cast<uint8_t*>(ptr);
  EXPECT_EQ(bytes[0], 0xAB);
  EXPECT_EQ(bytes[255], 0xAB);
}

TEST(DmaBufSimTest, MmapInvalidFdReturnsNull) {
  DmaBufSim sim;
  EXPECT_EQ(sim.Mmap(999), nullptr);
}

// ---- Export / Import ----

TEST(DmaBufSimTest, ExportAndImportSharesMemory) {
  DmaBufSim sim;
  int fd = sim.Allocate(128);

  // Write via mmap
  auto* ptr = static_cast<uint8_t*>(sim.Mmap(fd));
  ASSERT_NE(ptr, nullptr);
  ptr[0] = 0x42;
  ptr[127] = 0xFF;

  // Export
  EXPECT_TRUE(sim.Export(fd));

  // Import and verify shared memory
  auto* imported = static_cast<uint8_t*>(sim.Import(fd));
  ASSERT_NE(imported, nullptr);
  EXPECT_EQ(imported[0], 0x42);
  EXPECT_EQ(imported[127], 0xFF);

  // They should point to the same memory
  EXPECT_EQ(ptr, imported);
}

TEST(DmaBufSimTest, ImportWithoutExportFails) {
  DmaBufSim sim;
  int fd = sim.Allocate(64);
  EXPECT_EQ(sim.Import(fd), nullptr);
}

TEST(DmaBufSimTest, ExportInvalidFdFails) {
  DmaBufSim sim;
  EXPECT_FALSE(sim.Export(999));
}

// ---- BufferInfo ----

TEST(DmaBufSimTest, GetBufferInfoReturnsCorrectData) {
  constexpr uint64_t kBase = 0x20000000;
  DmaBufSim sim(kBase);

  int fd = sim.Allocate(4096);
  const auto* info = sim.GetBufferInfo(fd);
  ASSERT_NE(info, nullptr);

  EXPECT_EQ(info->fd, fd);
  EXPECT_EQ(info->size, 4096u);
  EXPECT_NE(info->virt_addr, nullptr);
  EXPECT_EQ(info->phys_addr, kBase);
  EXPECT_FALSE(info->exported);
}

TEST(DmaBufSimTest, PhysAddressesArePageAligned) {
  DmaBufSim sim(0x10000000);

  int fd1 = sim.Allocate(100);   // Not page-aligned size
  int fd2 = sim.Allocate(200);

  const auto* info1 = sim.GetBufferInfo(fd1);
  const auto* info2 = sim.GetBufferInfo(fd2);
  ASSERT_NE(info1, nullptr);
  ASSERT_NE(info2, nullptr);

  // Second buffer's phys_addr should be page-aligned after first
  EXPECT_EQ(info2->phys_addr % 4096, 0u);
  EXPECT_GT(info2->phys_addr, info1->phys_addr);
}

TEST(DmaBufSimTest, GetBufferInfoInvalidFdReturnsNull) {
  DmaBufSim sim;
  EXPECT_EQ(sim.GetBufferInfo(999), nullptr);
}

}  // namespace
