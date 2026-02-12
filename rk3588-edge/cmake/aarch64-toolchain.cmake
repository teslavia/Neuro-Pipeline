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

# RK3588 optimization flags (Cortex-A76 big cores + Cortex-A55 little cores)
set(CMAKE_C_FLAGS_RELEASE "-O3 -march=armv8.2-a -mtune=cortex-a76" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=armv8.2-a -mtune=cortex-a76" CACHE STRING "" FORCE)

# NOTE: We do NOT set CMAKE_SYSROOT because our sysroot only contains
# RKNN/MPP/RGA libs — not a full libc. Setting CMAKE_SYSROOT would hide
# the cross-compiler's built-in system headers (features.h, etc.).
# Instead, we add the SDK paths as additional include/link directories
# in the USE_MOCK_HAL=OFF block below.

option(USE_MOCK_HAL "Use mock HAL instead of real RK3588 SDK" ON)

if(NOT USE_MOCK_HAL)
  # Determine RK3588 SDK sysroot path
  if(DEFINED ENV{SYSROOT})
    set(RK3588_SDK_PATH $ENV{SYSROOT})
  else()
    set(RK3588_SDK_PATH /opt/rk3588-sysroot)
  endif()

  message(STATUS "Using real RK3588 SDK from: ${RK3588_SDK_PATH}")

  # Verify critical files exist
  if(NOT EXISTS "${RK3588_SDK_PATH}/usr/include/rknn_api.h")
    message(FATAL_ERROR
      "rknn_api.h not found in ${RK3588_SDK_PATH}.\n"
      "Run: bash tools/cross_compile_env/prepare_sysroot.sh")
  endif()

  if(NOT EXISTS "${RK3588_SDK_PATH}/usr/lib/librknnrt.so")
    message(FATAL_ERROR
      "librknnrt.so not found in ${RK3588_SDK_PATH}.\n"
      "Run: bash tools/cross_compile_env/prepare_sysroot.sh")
  endif()

  # Add SDK include/library paths (without replacing system paths)
  include_directories(SYSTEM
    ${RK3588_SDK_PATH}/usr/include
    ${RK3588_SDK_PATH}/usr/include/rockchip
    ${RK3588_SDK_PATH}/usr/include/rga
  )
  link_directories(${RK3588_SDK_PATH}/usr/lib)
else()
  message(STATUS "Using mock HAL (no real SDK required)")
endif()
