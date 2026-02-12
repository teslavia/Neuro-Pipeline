# CMake toolchain file for RK3588 (aarch64) cross-compilation
#
# Usage:
#   cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake/aarch64-toolchain.cmake
#
# Options:
#   -DUSE_MOCK_HAL=ON   Build with mock HAL (no real SDK needed)
#   -DUSE_MOCK_HAL=OFF  Build with real RKNN/MPP/RGA libraries

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Cross-compiler
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_AR aarch64-linux-gnu-ar)
set(CMAKE_RANLIB aarch64-linux-gnu-ranlib)
set(CMAKE_STRIP aarch64-linux-gnu-strip)

# Sysroot — only set when using real HAL (USE_MOCK_HAL=OFF).
# Our sysroot only contains RKNN/MPP/RGA libs, not a full libc,
# so setting CMAKE_SYSROOT in mock mode breaks standard header resolution.
option(USE_MOCK_HAL "Use mock HAL instead of real RK3588 SDK" ON)

if(NOT USE_MOCK_HAL)
  # Sysroot detection: environment > cmake arg > Docker default
  if(DEFINED ENV{SYSROOT})
    set(CMAKE_SYSROOT $ENV{SYSROOT})
  elseif(NOT CMAKE_SYSROOT)
    set(CMAKE_SYSROOT /opt/rk3588-sysroot)
  endif()

  # Search paths — programs from host, libraries/headers from sysroot + host
  set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})
  set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)

  message(STATUS "Using real RK3588 SDK from sysroot: ${CMAKE_SYSROOT}")

  # Additional include directories
  include_directories(
    ${CMAKE_SYSROOT}/usr/include
    ${CMAKE_SYSROOT}/usr/include/rockchip
    ${CMAKE_SYSROOT}/usr/include/rga
  )

  # Library search path
  link_directories(
    ${CMAKE_SYSROOT}/usr/lib
  )

  # Verify critical files exist
  if(NOT EXISTS "${CMAKE_SYSROOT}/usr/include/rknn_api.h")
    message(FATAL_ERROR
      "rknn_api.h not found in sysroot.\n"
      "Run: bash tools/cross_compile_env/prepare_sysroot.sh")
  endif()

  if(NOT EXISTS "${CMAKE_SYSROOT}/usr/lib/librknnrt.so")
    message(FATAL_ERROR
      "librknnrt.so not found in sysroot.\n"
      "Run: bash tools/cross_compile_env/prepare_sysroot.sh")
  endif()
else()
  message(STATUS "Using mock HAL (no real SDK required)")
endif()
