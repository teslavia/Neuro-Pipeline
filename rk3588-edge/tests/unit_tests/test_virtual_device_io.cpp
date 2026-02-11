#include <gtest/gtest.h>

#include <cstring>
#include <string>
#include <vector>

#include "common/virtual_device_io.hpp"

namespace {

using data_processing::VirtualDeviceIO;

// ---- Registration ----

TEST(VirtualDeviceIOTest, RegisterAndCheckExists) {
  VirtualDeviceIO vdev;
  EXPECT_TRUE(vdev.RegisterDevice("/dev/video0"));
  EXPECT_TRUE(vdev.DeviceExists("/dev/video0"));
  EXPECT_FALSE(vdev.DeviceExists("/dev/video1"));
}

TEST(VirtualDeviceIOTest, DuplicateRegistrationFails) {
  VirtualDeviceIO vdev;
  EXPECT_TRUE(vdev.RegisterDevice("/dev/rga"));
  EXPECT_FALSE(vdev.RegisterDevice("/dev/rga"));
}

// ---- Open / Close ----

TEST(VirtualDeviceIOTest, OpenReturnsValidFd) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/video0");

  int fd = vdev.Open("/dev/video0");
  EXPECT_GE(fd, 0);
  EXPECT_TRUE(vdev.IsOpen(fd));
}

TEST(VirtualDeviceIOTest, OpenUnregisteredDeviceFails) {
  VirtualDeviceIO vdev;
  EXPECT_EQ(vdev.Open("/dev/nonexistent"), -1);
}

TEST(VirtualDeviceIOTest, CloseValidFd) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/test");
  int fd = vdev.Open("/dev/test");

  EXPECT_EQ(vdev.Close(fd), 0);
  EXPECT_FALSE(vdev.IsOpen(fd));
}

TEST(VirtualDeviceIOTest, CloseInvalidFdFails) {
  VirtualDeviceIO vdev;
  EXPECT_EQ(vdev.Close(999), -1);
}

// ---- Read ----

TEST(VirtualDeviceIOTest, ReadDeviceContent) {
  VirtualDeviceIO vdev;
  std::vector<uint8_t> content = {0x48, 0x65, 0x6C, 0x6C, 0x6F};  // "Hello"
  vdev.RegisterDevice("/dev/test", content);

  int fd = vdev.Open("/dev/test");
  char buf[16] = {};
  ssize_t n = vdev.Read(fd, buf, sizeof(buf));

  EXPECT_EQ(n, 5);
  EXPECT_EQ(std::string(buf, 5), "Hello");
}

TEST(VirtualDeviceIOTest, ReadPartialThenRest) {
  VirtualDeviceIO vdev;
  std::vector<uint8_t> content = {1, 2, 3, 4, 5, 6};
  vdev.RegisterDevice("/dev/test", content);

  int fd = vdev.Open("/dev/test");

  uint8_t buf[3] = {};
  EXPECT_EQ(vdev.Read(fd, buf, 3), 3);
  EXPECT_EQ(buf[0], 1);
  EXPECT_EQ(buf[1], 2);
  EXPECT_EQ(buf[2], 3);

  EXPECT_EQ(vdev.Read(fd, buf, 3), 3);
  EXPECT_EQ(buf[0], 4);
  EXPECT_EQ(buf[1], 5);
  EXPECT_EQ(buf[2], 6);

  // EOF
  EXPECT_EQ(vdev.Read(fd, buf, 3), 0);
}

TEST(VirtualDeviceIOTest, ReadEmptyDevice) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/empty");
  int fd = vdev.Open("/dev/empty");

  char buf[4] = {};
  EXPECT_EQ(vdev.Read(fd, buf, 4), 0);
}

TEST(VirtualDeviceIOTest, ReadInvalidFdFails) {
  VirtualDeviceIO vdev;
  char buf[4] = {};
  EXPECT_EQ(vdev.Read(999, buf, 4), -1);
}

// ---- Write ----

TEST(VirtualDeviceIOTest, WriteAppendsContent) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/output");
  int fd = vdev.Open("/dev/output");

  const char* msg = "abc";
  EXPECT_EQ(vdev.Write(fd, msg, 3), 3);

  auto content = vdev.GetDeviceContent("/dev/output");
  EXPECT_EQ(content.size(), 3u);
  EXPECT_EQ(content[0], 'a');
  EXPECT_EQ(content[1], 'b');
  EXPECT_EQ(content[2], 'c');
}

TEST(VirtualDeviceIOTest, WriteInvalidFdFails) {
  VirtualDeviceIO vdev;
  EXPECT_EQ(vdev.Write(999, "x", 1), -1);
}

// ---- Ioctl ----

TEST(VirtualDeviceIOTest, IoctlCallsRegisteredHandler) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/video0");

  constexpr unsigned long kVIDIOC_QUERYCAP = 0x80685600;
  bool handler_called = false;

  vdev.RegisterIoctl("/dev/video0", kVIDIOC_QUERYCAP,
                     [&handler_called](unsigned long, void* arg) -> int {
                       handler_called = true;
                       if (arg) {
                         *static_cast<int*>(arg) = 42;
                       }
                       return 0;
                     });

  int fd = vdev.Open("/dev/video0");
  int result_val = 0;
  int ret = vdev.Ioctl(fd, kVIDIOC_QUERYCAP, &result_val);

  EXPECT_EQ(ret, 0);
  EXPECT_TRUE(handler_called);
  EXPECT_EQ(result_val, 42);
}

TEST(VirtualDeviceIOTest, IoctlUnregisteredRequestReturnsNegOne) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/test");
  int fd = vdev.Open("/dev/test");

  EXPECT_EQ(vdev.Ioctl(fd, 0xDEAD, nullptr), -1);
}

TEST(VirtualDeviceIOTest, IoctlInvalidFdFails) {
  VirtualDeviceIO vdev;
  EXPECT_EQ(vdev.Ioctl(999, 0, nullptr), -1);
}

// ---- Multiple Devices ----

TEST(VirtualDeviceIOTest, MultipleDevicesIndependent) {
  VirtualDeviceIO vdev;
  vdev.RegisterDevice("/dev/video0", {1, 2, 3});
  vdev.RegisterDevice("/dev/video1", {10, 20, 30});

  int fd0 = vdev.Open("/dev/video0");
  int fd1 = vdev.Open("/dev/video1");

  uint8_t buf[3] = {};
  vdev.Read(fd0, buf, 3);
  EXPECT_EQ(buf[0], 1);

  vdev.Read(fd1, buf, 3);
  EXPECT_EQ(buf[0], 10);
}

}  // namespace
