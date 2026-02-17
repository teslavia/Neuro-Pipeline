cmake_minimum_required(VERSION 3.20)

# ==============================================================================
# GoogleTest — use local vendored copy (avoids network dependency in Docker)
# ==============================================================================
set(GOOGLETEST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/googletest")
if(EXISTS "${GOOGLETEST_DIR}/CMakeLists.txt")
  # Prevent overriding parent project compiler/linker settings
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  add_subdirectory("${GOOGLETEST_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/googletest")
else()
  # Fallback: fetch from network
  include(FetchContent)
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
  )
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)
endif()

include(GoogleTest)

# ==============================================================================
# Unit Tests
# ==============================================================================
set(UNIT_TEST_SOURCES
  unit_tests/test_memory_pool.cpp
  unit_tests/test_thread_pool.cpp
  unit_tests/test_zero_copy_buffer.cpp
  unit_tests/test_yolo_postprocess.cpp
  unit_tests/test_grpc_client.cpp
  unit_tests/test_mmap_ipc.cpp
  unit_tests/test_npu_scheduler.cpp
  unit_tests/test_cache_analysis.cpp
  unit_tests/test_neon_image_ops.cpp
  unit_tests/test_dmabuf_sim.cpp
  unit_tests/test_virtual_device_io.cpp
  unit_tests/test_hal_basic.cpp
  unit_tests/test_multi_model_manager.cpp
  unit_tests/test_multi_model_scheduler.cpp
  unit_tests/test_temporal_tracker.cpp
  unit_tests/test_adaptive_fps.cpp
  unit_tests/test_yolov8_postprocess.cpp
  unit_tests/test_config_manager.cpp
)

add_executable(run_unit_tests ${UNIT_TEST_SOURCES})

target_include_directories(run_unit_tests PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../include
  ${CMAKE_CURRENT_SOURCE_DIR}/../src
  ${CMAKE_CURRENT_SOURCE_DIR}/../src/generated
)

target_link_libraries(run_unit_tests
  PRIVATE
    neuro_edge_lib
    GTest::gtest
    GTest::gtest_main
    Threads::Threads
)

gtest_discover_tests(run_unit_tests)

# ==============================================================================
# Integration Tests (optional, requires hardware or mocks)
# ==============================================================================
option(BUILD_INTEGRATION_TESTS "Build integration tests" OFF)

if(BUILD_INTEGRATION_TESTS)
  set(INTEGRATION_TEST_SOURCES
    integration_tests/test_hal_pipeline.cpp
    integration_tests/test_grpc_communication.cpp
    integration_tests/test_perf_benchmark.cpp
  )

  add_executable(run_integration_tests ${INTEGRATION_TEST_SOURCES})

  target_include_directories(run_integration_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
    ${CMAKE_CURRENT_SOURCE_DIR}/../src
  )

  target_link_libraries(run_integration_tests
    PRIVATE
      neuro_edge_lib
      GTest::gtest
      GTest::gtest_main
      Threads::Threads
  )

  gtest_discover_tests(run_integration_tests)
endif()

# ==============================================================================
# Custom Targets
# ==============================================================================
add_custom_target(check
  COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
  DEPENDS run_unit_tests
  COMMENT "Running all unit tests"
)
