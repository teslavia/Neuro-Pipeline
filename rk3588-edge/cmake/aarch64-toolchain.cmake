# CMake toolchain file for RK3588 (aarch64) cross-compilation
#
# Usage:
#   cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake/aarch64-toolchain.cmake

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Cross-compiler
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_AR aarch64-linux-gnu-ar)
set(CMAKE_RANLIB aarch64-linux-gnu-ranlib)
set(CMAKE_STRIP aarch64-linux-gnu-strip)

# Sysroot (set via environment or override here)
if(DEFINED ENV{SYSROOT})
  set(CMAKE_SYSROOT $ENV{SYSROOT})
elseif(NOT CMAKE_SYSROOT)
  set(CMAKE_SYSROOT /opt/rk3588-sysroot)
endif()

# Search paths
set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# RK3588 optimization flags (Cortex-A76 big cores + Cortex-A55 little cores)
set(CMAKE_C_FLAGS_RELEASE "-O3 -march=armv8.2-a -mtune=cortex-a76" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=armv8.2-a -mtune=cortex-a76" CACHE STRING "" FORCE)
