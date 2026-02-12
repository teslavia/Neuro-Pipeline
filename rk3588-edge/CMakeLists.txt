cmake_minimum_required(VERSION 3.20)
project(neuro_pipeline_edge VERSION 1.0.0 LANGUAGES CXX)

# ==============================================================================
# C++ Standard
# ==============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type default
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -Wpedantic")
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -DDEBUG")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# Export compile commands for clangd / IDE
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ==============================================================================
# Options
# ==============================================================================
option(BUILD_TESTING "Build unit and integration tests" ON)
option(USE_MOCK_HAL "Use mock HAL for development without RK3588 hardware" OFF)

# ==============================================================================
# Dependencies
# ==============================================================================

# Threads (required)
find_package(Threads REQUIRED)

# Protobuf — when cross-compiling, protoc runs on host and code is pre-generated.
# We only need the protobuf headers/library for compilation, which may not be in
# the aarch64 sysroot. Use find_package when available, otherwise fall back to
# the host-installed protobuf headers (accessible outside sysroot in Docker).
if(CMAKE_CROSSCOMPILING)
  # In cross-compile Docker container, protobuf is installed as a host package.
  # Temporarily bypass sysroot to find it.
  set(_saved_root_mode ${CMAKE_FIND_ROOT_PATH_MODE_INCLUDE})
  set(_saved_lib_mode ${CMAKE_FIND_ROOT_PATH_MODE_LIBRARY})
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
  find_package(Protobuf QUIET)
  set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ${_saved_root_mode})
  set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ${_saved_lib_mode})
  if(NOT Protobuf_FOUND)
    message(STATUS "Protobuf not found via find_package in cross-compile — using pre-generated code")
    # Manually set protobuf include/lib from host paths
    find_path(Protobuf_INCLUDE_DIRS google/protobuf/message.h
      PATHS /usr/include NO_CMAKE_FIND_ROOT_PATH)
    find_library(Protobuf_LIBRARIES NAMES protobuf
      PATHS /usr/lib /usr/lib/aarch64-linux-gnu NO_CMAKE_FIND_ROOT_PATH)
    if(Protobuf_INCLUDE_DIRS)
      include_directories(${Protobuf_INCLUDE_DIRS})
    endif()
  else()
    include_directories(${Protobuf_INCLUDE_DIRS})
  endif()
else()
  find_package(Protobuf REQUIRED)
  include_directories(${Protobuf_INCLUDE_DIRS})
endif()

# gRPC (try cmake config first, fallback to pkg-config)
# When cross-compiling, also search host paths
find_package(gRPC CONFIG QUIET)
if(gRPC_FOUND)
  set(GRPC_LIBS gRPC::grpc++ gRPC::grpc)
  message(STATUS "Found gRPC via CMake config")
else()
  if(CMAKE_CROSSCOMPILING)
    find_library(GRPCPP_LIBRARY NAMES grpc++ PATHS /usr/lib /usr/lib/aarch64-linux-gnu NO_CMAKE_FIND_ROOT_PATH)
    find_library(GRPC_LIBRARY NAMES grpc PATHS /usr/lib /usr/lib/aarch64-linux-gnu NO_CMAKE_FIND_ROOT_PATH)
    find_path(GRPC_INCLUDE_DIR grpc/grpc.h PATHS /usr/include NO_CMAKE_FIND_ROOT_PATH)
  else()
    find_library(GRPCPP_LIBRARY NAMES grpc++)
    find_library(GRPC_LIBRARY NAMES grpc)
    find_path(GRPC_INCLUDE_DIR grpc/grpc.h)
  endif()
  if(GRPCPP_LIBRARY AND GRPC_LIBRARY)
    set(GRPC_LIBS ${GRPCPP_LIBRARY} ${GRPC_LIBRARY})
    include_directories(${GRPC_INCLUDE_DIR})
    message(STATUS "Found gRPC via find_library: ${GRPCPP_LIBRARY}")
  else()
    message(WARNING "gRPC not found - communication module will not build")
    set(GRPC_LIBS "")
  endif()
endif()

# RK3588 Platform Libraries (only when cross-compiling for ARM64)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" AND NOT USE_MOCK_HAL)
  find_library(RKNN_API_LIBRARY NAMES rknnrt PATHS /usr/lib)
  find_library(RGA_LIBRARY NAMES rga PATHS /usr/lib)
  find_library(MPP_LIBRARY NAMES rockchip_mpp PATHS /usr/lib)
  find_library(DRM_LIBRARY NAMES drm)

  if(NOT RKNN_API_LIBRARY)
    message(WARNING "RKNN runtime not found - AI inference module disabled")
  endif()

  set(PLATFORM_LIBS
    ${RKNN_API_LIBRARY}
    ${RGA_LIBRARY}
    ${MPP_LIBRARY}
    ${DRM_LIBRARY}
  )
  # Filter out NOTFOUND entries
  list(FILTER PLATFORM_LIBS EXCLUDE REGEX ".*-NOTFOUND$")
else()
  message(STATUS "Mock HAL mode or non-ARM64 build: platform libraries skipped")
  set(PLATFORM_LIBS "")
  add_compile_definitions(USE_MOCK_HAL=1)
endif()

# ==============================================================================
# Include Directories
# ==============================================================================
include_directories(
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${CMAKE_CURRENT_SOURCE_DIR}/src/generated
)

# ==============================================================================
# Protobuf Code Generation
# ==============================================================================
set(PROTO_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../proto")
set(PROTO_FILE "${PROTO_PATH}/neuro_pipeline.proto")
set(GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/generated")

file(MAKE_DIRECTORY ${GENERATED_DIR})

set(PROTO_SRCS "${GENERATED_DIR}/neuro_pipeline.pb.cc")
set(PROTO_HDRS "${GENERATED_DIR}/neuro_pipeline.pb.h")
set(GRPC_SRCS "${GENERATED_DIR}/neuro_pipeline.grpc.pb.cc")
set(GRPC_HDRS "${GENERATED_DIR}/neuro_pipeline.grpc.pb.h")

# Find grpc_cpp_plugin
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin)

if(Protobuf_PROTOC_EXECUTABLE AND GRPC_CPP_PLUGIN)
  add_custom_command(
    OUTPUT ${PROTO_SRCS} ${PROTO_HDRS} ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND ${Protobuf_PROTOC_EXECUTABLE}
    ARGS --cpp_out=${GENERATED_DIR}
         --grpc_out=${GENERATED_DIR}
         --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
         -I${PROTO_PATH}
         ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Generating C++ Protobuf and gRPC code"
  )
  message(STATUS "Protobuf code generation configured")
else()
  message(WARNING "protoc or grpc_cpp_plugin not found - using pre-generated code")
endif()

# ==============================================================================
# Source Files
# ==============================================================================

set(HAL_SOURCES
  src/hal/v4l2_camera.cpp
  src/hal/mpp_decoder.cpp
  src/hal/rga_processor.cpp
  src/hal/drm_allocator.cpp
  src/hal/dmabuf_sim.cpp
)

set(DATA_PROCESSING_SOURCES
  src/data_processing/zero_copy_buffer.cpp
  src/data_processing/memory_pool.cpp
  src/data_processing/thread_pool.cpp
  src/data_processing/mmap_ipc.cpp
  src/data_processing/cache_analysis.cpp
  src/data_processing/neon_image_ops.cpp
  src/data_processing/virtual_device_io.cpp
)

set(AI_INFERENCE_SOURCES
  src/ai_inference/rknn_engine.cpp
  src/ai_inference/yolo_postprocess.cpp
  src/ai_inference/npu_scheduler.cpp
)

set(COMMUNICATION_SOURCES
  src/communication/grpc_client.cpp
)

set(APP_SOURCES
  src/app/edge_main.cpp
  src/app/pipeline_coordinator.cpp
  src/app/config_manager.cpp
)

# Conditionally include generated protobuf sources
if(EXISTS "${PROTO_SRCS}" OR GRPC_CPP_PLUGIN)
  set(GENERATED_SOURCES ${PROTO_SRCS} ${GRPC_SRCS})
else()
  set(GENERATED_SOURCES "")
endif()

# Library target (everything except main)
add_library(neuro_edge_lib STATIC
  ${HAL_SOURCES}
  ${DATA_PROCESSING_SOURCES}
  ${AI_INFERENCE_SOURCES}
  ${COMMUNICATION_SOURCES}
  src/app/pipeline_coordinator.cpp
  src/app/config_manager.cpp
  ${GENERATED_SOURCES}
)

target_link_libraries(neuro_edge_lib
  PUBLIC
    ${Protobuf_LIBRARIES}
    ${GRPC_LIBS}
    ${PLATFORM_LIBS}
    Threads::Threads
)

# Main executable
add_executable(neuro_pipeline_edge src/app/edge_main.cpp)
target_link_libraries(neuro_pipeline_edge PRIVATE neuro_edge_lib)

# ==============================================================================
# Testing
# ==============================================================================
if(BUILD_TESTING)
  enable_testing()
  add_subdirectory(tests)
endif()

# ==============================================================================
# Installation
# ==============================================================================
install(TARGETS neuro_pipeline_edge RUNTIME DESTINATION bin)
install(DIRECTORY models/ DESTINATION share/neuro-pipeline/models
  FILES_MATCHING PATTERN "*.rknn"
)
