# Test Suite

## Overview

- **Unit Tests**: `unit_tests/` - Fast, isolated tests (101 tests)
- **Integration Tests**: `integration_tests/` - Hardware-dependent tests (1 test)

## Running Tests

### Local Development (Mock HAL)
```bash
cd rk3588-edge/build
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON
make -j$(nproc)
ctest --output-on-failure
```

### Device Testing (Real HAL)
```bash
# Cross-compile
USE_MOCK_HAL=OFF bash tools/cross_compile_env/build_rk3588.sh

# Deploy and run on device
scp rk3588-edge/build/neuro_pipeline_tests rock@192.168.1.70:/tmp/
ssh rock@192.168.1.70 "cd /tmp && ./neuro_pipeline_tests"
```

### Performance Benchmark
```bash
# On device only
./neuro_pipeline_tests --gtest_also_run_disabled_tests --gtest_filter=PerfBenchmark.DISABLED_E2ELatency
```

## Test Categories

### Unit Tests
- `test_buffer.cpp` - Buffer management
- `test_memory_pool.cpp` - Memory allocation
- `test_thread_pool.cpp` - Thread scheduling
- `test_zero_copy_buffer.cpp` - DMA-BUF simulation
- `test_nms.cpp` - NMS algorithm
- `test_yolo_postprocess.cpp` - YOLO decoder
- `test_hal_basic.cpp` - HAL initialization (Mock only)

### Integration Tests
- `test_perf_benchmark.cpp` - End-to-end performance (Device only, disabled by default)

## Notes

- HAL tests require `USE_MOCK_HAL=ON` for CI/local development
- Performance benchmark requires real hardware and is disabled by default
- Use `--gtest_filter` to run specific tests
- Use `--gtest_also_run_disabled_tests` to run disabled tests
