#include "neuro/pipeline/cache_analysis.hpp"

#include <algorithm>
#include <chrono>
#include <numeric>

namespace neuro::pipeline {

uint64_t CacheAnalysis::SumRowMajor(const std::vector<uint32_t>& matrix,
                                     size_t rows, size_t cols) {
  uint64_t sum = 0;
  for (size_t r = 0; r < rows; ++r) {
    for (size_t c = 0; c < cols; ++c) {
      sum += matrix[r * cols + c];
    }
  }
  return sum;
}

uint64_t CacheAnalysis::SumColumnMajor(const std::vector<uint32_t>& matrix,
                                        size_t rows, size_t cols) {
  uint64_t sum = 0;
  for (size_t c = 0; c < cols; ++c) {
    for (size_t r = 0; r < rows; ++r) {
      sum += matrix[r * cols + c];
    }
  }
  return sum;
}

uint64_t CacheAnalysis::SumSequential(const std::vector<uint32_t>& data) {
  uint64_t sum = 0;
  for (size_t i = 0; i < data.size(); ++i) {
    sum += data[i];
  }
  return sum;
}

uint64_t CacheAnalysis::SumStrided(const std::vector<uint32_t>& data,
                                    size_t stride) {
  if (stride == 0) stride = 1;
  uint64_t sum = 0;
  for (size_t i = 0; i < data.size(); i += stride) {
    sum += data[i];
  }
  return sum;
}

CacheAnalysis::BenchmarkResult CacheAnalysis::BenchmarkMatrixTraversal(
    size_t rows, size_t cols, int iterations) {
  std::vector<uint32_t> matrix(rows * cols);
  std::iota(matrix.begin(), matrix.end(), 1u);

  // Warm up
  volatile uint64_t sink = SumRowMajor(matrix, rows, cols);
  sink = SumColumnMajor(matrix, rows, cols);
  (void)sink;

  // Benchmark row-major (cache-friendly)
  auto start = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iterations; ++i) {
    sink = SumRowMajor(matrix, rows, cols);
  }
  auto end = std::chrono::high_resolution_clock::now();
  double row_ns =
      std::chrono::duration<double, std::nano>(end - start).count() /
      iterations;

  // Benchmark column-major (cache-unfriendly)
  start = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iterations; ++i) {
    sink = SumColumnMajor(matrix, rows, cols);
  }
  end = std::chrono::high_resolution_clock::now();
  double col_ns =
      std::chrono::duration<double, std::nano>(end - start).count() /
      iterations;

  BenchmarkResult result{};
  result.sequential_ns = row_ns;
  result.strided_ns = col_ns;
  result.speedup_ratio = (row_ns > 0) ? col_ns / row_ns : 1.0;
  result.elements = rows * cols;
  return result;
}

CacheAnalysis::BenchmarkResult CacheAnalysis::BenchmarkStridedAccess(
    size_t array_size, size_t stride, int iterations) {
  std::vector<uint32_t> data(array_size);
  std::iota(data.begin(), data.end(), 1u);

  volatile uint64_t sink = SumSequential(data);
  sink = SumStrided(data, stride);
  (void)sink;

  auto start = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iterations; ++i) {
    sink = SumSequential(data);
  }
  auto end = std::chrono::high_resolution_clock::now();
  double seq_ns =
      std::chrono::duration<double, std::nano>(end - start).count() /
      iterations;

  start = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iterations; ++i) {
    sink = SumStrided(data, stride);
  }
  end = std::chrono::high_resolution_clock::now();
  double str_ns =
      std::chrono::duration<double, std::nano>(end - start).count() /
      iterations;

  BenchmarkResult result{};
  result.sequential_ns = seq_ns;
  result.strided_ns = str_ns;
  result.speedup_ratio = (seq_ns > 0) ? str_ns / seq_ns : 1.0;
  result.elements = array_size;
  return result;
}

}  // namespace data_processing
