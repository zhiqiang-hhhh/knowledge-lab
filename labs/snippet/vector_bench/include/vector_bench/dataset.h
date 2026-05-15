#pragma once

#include "benchmark_config.h"

#include <cstdint>
#include <string>
#include <vector>

namespace vecbench {

struct BenchmarkDataset {
  int dim = 0;
  int nb = 0;
  int nq = 0;
  int k = 0;
  std::vector<float> base;
  std::vector<float> queries;
  std::vector<std::int64_t> ground_truth;
};

class DatasetBuilder {
public:
  explicit DatasetBuilder(const DatasetConfig& cfg);

  BenchmarkDataset build();

private:
  void generateData(BenchmarkDataset& dataset);
  void loadData(BenchmarkDataset& dataset);
  void saveData(const BenchmarkDataset& dataset) const;
  void computeGroundTruth(BenchmarkDataset& dataset);
  static void normalize(float* vectors, int n, int d);

  static bool fileExists(const std::string& path);
  static bool loadFVecs(const std::string& path, std::vector<float>& data, int expected_n, int expected_d);
  static bool loadIVecs(const std::string& path, std::vector<std::int64_t>& data, int expected_n, int expected_d);
  static void saveFVecs(const std::string& path, const std::vector<float>& data, int n, int d);
  static void saveIVecs(const std::string& path, const std::vector<std::int64_t>& data, int n, int d);

  DatasetConfig config_;
};

} // namespace vecbench
