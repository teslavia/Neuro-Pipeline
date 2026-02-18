#include <gtest/gtest.h>

#include <numeric>
#include <vector>

#include "neuro/pipeline/cache_analysis.hpp"

namespace {

using neuro::pipeline::CacheAnalysis;

// ---- Correctness Tests ----

TEST(CacheAnalysisTest, SumRowMajorCorrectness) {
  // 3x4 matrix: [1,2,3,4, 5,6,7,8, 9,10,11,12]
  std::vector<uint32_t> matrix(12);
  std::iota(matrix.begin(), matrix.end(), 1u);

  uint64_t sum = CacheAnalysis::SumRowMajor(matrix, 3, 4);
  EXPECT_EQ(sum, 78u);  // 1+2+...+12 = 78
}

TEST(CacheAnalysisTest, SumColumnMajorCorrectness) {
  std::vector<uint32_t> matrix(12);
  std::iota(matrix.begin(), matrix.end(), 1u);

  uint64_t sum = CacheAnalysis::SumColumnMajor(matrix, 3, 4);
  // Column-major visits same elements, just different order → same sum
  EXPECT_EQ(sum, 78u);
}

TEST(CacheAnalysisTest, RowMajorAndColumnMajorProduceSameSum) {
  constexpr size_t kRows = 64;
  constexpr size_t kCols = 64;
  std::vector<uint32_t> matrix(kRows * kCols);
  std::iota(matrix.begin(), matrix.end(), 1u);

  uint64_t row_sum = CacheAnalysis::SumRowMajor(matrix, kRows, kCols);
  uint64_t col_sum = CacheAnalysis::SumColumnMajor(matrix, kRows, kCols);
  EXPECT_EQ(row_sum, col_sum);
}

TEST(CacheAnalysisTest, SumSequentialCorrectness) {
  std::vector<uint32_t> data = {10, 20, 30, 40, 50};
  EXPECT_EQ(CacheAnalysis::SumSequential(data), 150u);
}

TEST(CacheAnalysisTest, SumSequentialEmpty) {
  std::vector<uint32_t> data;
  EXPECT_EQ(CacheAnalysis::SumSequential(data), 0u);
}

TEST(CacheAnalysisTest, SumStridedStride1EqualsSumSequential) {
  std::vector<uint32_t> data(100);
  std::iota(data.begin(), data.end(), 1u);

  EXPECT_EQ(CacheAnalysis::SumStrided(data, 1),
            CacheAnalysis::SumSequential(data));
}

TEST(CacheAnalysisTest, SumStridedStride2) {
  // data = {1,2,3,4,5,6,7,8}
  // stride=2 → indices 0,2,4,6 → values 1,3,5,7 = 16
  std::vector<uint32_t> data(8);
  std::iota(data.begin(), data.end(), 1u);

  EXPECT_EQ(CacheAnalysis::SumStrided(data, 2), 16u);
}

TEST(CacheAnalysisTest, SumStridedLargerThanSize) {
  std::vector<uint32_t> data = {42, 99, 100};
  // stride=10 → only index 0 visited
  EXPECT_EQ(CacheAnalysis::SumStrided(data, 10), 42u);
}

TEST(CacheAnalysisTest, SumStridedZeroStrideFallsBackToOne) {
  std::vector<uint32_t> data = {1, 2, 3};
  // stride=0 should be treated as stride=1
  EXPECT_EQ(CacheAnalysis::SumStrided(data, 0), 6u);
}

// ---- Benchmark Integration Tests ----

TEST(CacheAnalysisTest, BenchmarkMatrixTraversalReturnsValidResult) {
  auto result = CacheAnalysis::BenchmarkMatrixTraversal(64, 64, 2);
  EXPECT_GT(result.sequential_ns, 0.0);
  EXPECT_GT(result.strided_ns, 0.0);
  EXPECT_GT(result.speedup_ratio, 0.0);
  EXPECT_EQ(result.elements, 64u * 64u);
}

TEST(CacheAnalysisTest, BenchmarkStridedAccessReturnsValidResult) {
  auto result = CacheAnalysis::BenchmarkStridedAccess(1024, 16, 2);
  EXPECT_GT(result.sequential_ns, 0.0);
  EXPECT_GT(result.strided_ns, 0.0);
  EXPECT_GT(result.speedup_ratio, 0.0);
  EXPECT_EQ(result.elements, 1024u);
}

TEST(CacheAnalysisTest, SingleRowMatrixRowMajor) {
  std::vector<uint32_t> matrix = {5, 10, 15};
  EXPECT_EQ(CacheAnalysis::SumRowMajor(matrix, 1, 3), 30u);
  EXPECT_EQ(CacheAnalysis::SumColumnMajor(matrix, 1, 3), 30u);
}

}  // namespace
