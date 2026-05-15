#pragma once

#include "benchmark_config.h"

#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace vecbench {

struct TimingMetrics {
  double train_s = 0.0;
  double add_s = 0.0;
  double build_s = 0.0;
  double sequential_ms_per_query = 0.0;
  double sequential_total_s = 0.0;
  double concurrent_ms_per_query = 0.0;
  double concurrent_total_s = 0.0;
  std::size_t concurrency = 0;
};

struct RecallMetrics {
  double recall_at_1 = 0.0;
  double recall_at_5 = 0.0;
  double recall_at_k = 0.0;
};

struct ResourceMetrics {
  double serialized_index_mb = 0.0;
  double compression_ratio = 0.0;
};

struct BenchmarkResult {
  std::string library;
  std::string method;
  std::map<std::string, std::string> parameters;
  DatasetConfig dataset;
  TimingMetrics timing;
  RecallMetrics recall;
  ResourceMetrics resources;
};

using BenchmarkResults = std::vector<BenchmarkResult>;

} // namespace vecbench
