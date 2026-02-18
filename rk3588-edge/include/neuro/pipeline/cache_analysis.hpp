#ifndef NEURO_PIPELINE_CACHE_ANALYSIS_HPP_
#define NEURO_PIPELINE_CACHE_ANALYSIS_HPP_

#include <cstddef>
#include <cstdint>
#include <vector>

namespace neuro::pipeline {

/**
 * @brief Cache-friendly vs cache-unfriendly memory access pattern analysis.
 *
 * Demonstrates the performance impact of memory access patterns on
 * ARM Cortex-A76 (RK3588). Compares row-major (cache-friendly) vs
 * column-major (cache-unfriendly) traversals on 2D matrices, plus
 * sequential vs strided access patterns.
 *
 * Used for education and benchmarking — shows why zero-copy pipelines
 * and contiguous buffer layouts matter for real-time inference.
 */
class CacheAnalysis {
 public:
  struct BenchmarkResult {
    double sequential_ns;   ///< Time for sequential (cache-friendly) access
    double strided_ns;      ///< Time for strided (cache-unfriendly) access
    double speedup_ratio;   ///< sequential / strided (>1 means sequential wins)
    size_t elements;        ///< Number of elements processed
  };

  /// Run row-major vs column-major matrix traversal benchmark.
  /// @param rows Matrix rows
  /// @param cols Matrix columns
  /// @param iterations Number of repetitions for stable timing
  /// @return BenchmarkResult with row-major as sequential, col-major as strided
  static BenchmarkResult BenchmarkMatrixTraversal(
      size_t rows, size_t cols, int iterations = 10);

  /// Run sequential vs strided array access benchmark.
  /// @param array_size Number of elements
  /// @param stride Access stride (1 = sequential, N = every Nth element)
  /// @param iterations Number of repetitions
  static BenchmarkResult BenchmarkStridedAccess(
      size_t array_size, size_t stride, int iterations = 10);

  /// Sum array elements in row-major (sequential) order.
  /// Returns sum to prevent compiler from optimizing away the access.
  static uint64_t SumRowMajor(const std::vector<uint32_t>& matrix,
                              size_t rows, size_t cols);

  /// Sum array elements in column-major (strided) order.
  static uint64_t SumColumnMajor(const std::vector<uint32_t>& matrix,
                                 size_t rows, size_t cols);

  /// Sum array with sequential access (stride = 1).
  static uint64_t SumSequential(const std::vector<uint32_t>& data);

  /// Sum array with strided access.
  static uint64_t SumStrided(const std::vector<uint32_t>& data, size_t stride);
};

}  // namespace neuro::pipeline

#endif  // NEURO_PIPELINE_CACHE_ANALYSIS_HPP_
