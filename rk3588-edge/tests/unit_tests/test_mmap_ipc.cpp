#include <gtest/gtest.h>

#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "neuro/pipeline/mmap_ipc.hpp"

namespace {

const std::string kTestShmName = "/neuro_test_shm";

class MmapIPCTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Clean up any leftover shared memory from previous failed tests
    neuro::pipeline::MmapSharedMemory::Unlink(kTestShmName);
  }

  void TearDown() override {
    neuro::pipeline::MmapSharedMemory::Unlink(kTestShmName);
  }
};

TEST_F(MmapIPCTest, CreateAndValidate) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 4096, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  EXPECT_TRUE(shm.IsValid());
  EXPECT_EQ(shm.Size(), 4096u);
  EXPECT_NE(shm.Data(), nullptr);
  EXPECT_EQ(shm.Name(), kTestShmName);
}

TEST_F(MmapIPCTest, WriteAndReadBack) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 1024, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  const char* message = "Hello from mmap IPC!";
  size_t msg_len = std::strlen(message) + 1;

  size_t written = shm.Write(message, msg_len);
  EXPECT_EQ(written, msg_len);

  char buffer[64] = {};
  size_t read_bytes = shm.Read(buffer, msg_len);
  EXPECT_EQ(read_bytes, msg_len);
  EXPECT_STREQ(buffer, message);
}

TEST_F(MmapIPCTest, WriteAtOffset) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 256, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  uint32_t val1 = 0xDEADBEEF;
  uint32_t val2 = 0xCAFEBABE;

  shm.Write(&val1, sizeof(val1), 0);
  shm.Write(&val2, sizeof(val2), sizeof(val1));

  uint32_t read1 = 0, read2 = 0;
  shm.Read(&read1, sizeof(read1), 0);
  shm.Read(&read2, sizeof(read2), sizeof(read1));

  EXPECT_EQ(read1, 0xDEADBEEFu);
  EXPECT_EQ(read2, 0xCAFEBABEu);
}

TEST_F(MmapIPCTest, BoundaryProtection) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 16, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  // Write more than size — should be clamped
  std::vector<uint8_t> large_data(100, 0xAA);
  size_t written = shm.Write(large_data.data(), large_data.size());
  EXPECT_EQ(written, 16u);

  // Read beyond size — should be clamped
  std::vector<uint8_t> read_buf(100, 0);
  size_t read_bytes = shm.Read(read_buf.data(), read_buf.size());
  EXPECT_EQ(read_bytes, 16u);

  // Verify only 16 bytes were filled
  for (size_t i = 0; i < 16; ++i) {
    EXPECT_EQ(read_buf[i], 0xAAu);
  }
}

TEST_F(MmapIPCTest, ReadBeyondSizeReturnsZero) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 16, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  char buf[4] = {};
  // Offset beyond size
  size_t read_bytes = shm.Read(buf, 4, 20);
  EXPECT_EQ(read_bytes, 0u);
}

TEST_F(MmapIPCTest, CreatorConsumerSharing) {
  // Creator writes data
  {
    neuro::pipeline::MmapSharedMemory creator(
        kTestShmName, 256, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

    uint64_t frame_id = 12345;
    float confidence = 0.95f;
    creator.Write(&frame_id, sizeof(frame_id), 0);
    creator.Write(&confidence, sizeof(confidence), sizeof(frame_id));

    // Consumer opens same shared memory and reads
    neuro::pipeline::MmapSharedMemory consumer(
        kTestShmName, 0, neuro::pipeline::MmapSharedMemory::Mode::kOpen);

    EXPECT_TRUE(consumer.IsValid());
    // macOS rounds up to page size (16384), so check >= instead of ==
    EXPECT_GE(consumer.Size(), 256u);

    uint64_t read_frame = 0;
    float read_conf = 0.0f;
    consumer.Read(&read_frame, sizeof(read_frame), 0);
    consumer.Read(&read_conf, sizeof(read_conf), sizeof(read_frame));

    EXPECT_EQ(read_frame, 12345u);
    EXPECT_FLOAT_EQ(read_conf, 0.95f);
  }
}

TEST_F(MmapIPCTest, DirectMemoryAccess) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 4096, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  // Write directly via Data() pointer
  auto* ptr = static_cast<uint8_t*>(shm.Data());
  for (int i = 0; i < 256; ++i) {
    ptr[i] = static_cast<uint8_t>(i);
  }

  // Read directly
  for (int i = 0; i < 256; ++i) {
    EXPECT_EQ(ptr[i], static_cast<uint8_t>(i));
  }
}

TEST_F(MmapIPCTest, MoveSemantics) {
  neuro::pipeline::MmapSharedMemory shm1(
      kTestShmName, 512, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  EXPECT_TRUE(shm1.IsValid());

  // Move construct
  neuro::pipeline::MmapSharedMemory shm2(std::move(shm1));
  EXPECT_TRUE(shm2.IsValid());
  EXPECT_FALSE(shm1.IsValid());  // NOLINT: testing moved-from state
  EXPECT_EQ(shm2.Size(), 512u);
}

TEST_F(MmapIPCTest, ConcurrentReadWrite) {
  neuro::pipeline::MmapSharedMemory shm(
      kTestShmName, 4096, neuro::pipeline::MmapSharedMemory::Mode::kCreate);

  auto* shared = static_cast<std::atomic<int>*>(shm.Data());
  shared->store(0);

  constexpr int kIterations = 10000;

  // Writer thread
  std::thread writer([shared]() {
    for (int i = 0; i < kIterations; ++i) {
      shared->fetch_add(1, std::memory_order_relaxed);
    }
  });

  // Reader thread
  std::thread reader([shared]() {
    for (int i = 0; i < kIterations; ++i) {
      shared->fetch_add(1, std::memory_order_relaxed);
    }
  });

  writer.join();
  reader.join();

  EXPECT_EQ(shared->load(), 2 * kIterations);
}

}  // namespace
