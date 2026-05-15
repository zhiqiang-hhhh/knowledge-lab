#pragma once

#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace vecbench {

struct DatasetConfig {
  int dim = 128;
  int nb = 20000;
  int nq = 500;
  int k = 10;
  unsigned int seed = 42;
  bool normalize = true;
  std::string save_data_dir;
  std::string load_data_dir;
};

struct SearchConfig {
  bool run_sequential = true;
  bool run_concurrent = true;
  std::size_t concurrency = 0; // 0 -> use hardware concurrency
  bool verify_concurrent = false; // optionally compare sequential & concurrent results
};

struct OutputConfig {
  std::string csv_path = "vecbench_results.csv";
  bool pretty_print = true;
  bool include_header = true;
};

struct AlgorithmSpec {
  std::string library;  // e.g. "faiss"
  std::string name;     // e.g. "hnsw_flat"
  std::map<std::string, std::string> params;
};

struct BenchmarkConfig {
  DatasetConfig dataset;
  SearchConfig search;
  OutputConfig output;
  std::vector<AlgorithmSpec> algorithms;
};

} // namespace vecbench
