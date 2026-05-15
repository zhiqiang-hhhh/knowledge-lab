#include "../include/vector_bench/dataset.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <random>
#include <stdexcept>

namespace vecbench {

DatasetBuilder::DatasetBuilder(const DatasetConfig& cfg) : config_(cfg) {}

BenchmarkDataset DatasetBuilder::build() {
  BenchmarkDataset dataset;
  dataset.dim = config_.dim;
  dataset.nb = config_.nb;
  dataset.nq = config_.nq;
  dataset.k = config_.k;

  if (!config_.load_data_dir.empty()) {
    loadData(dataset);
  }

  if (dataset.base.empty() || dataset.queries.empty()) {
    generateData(dataset);
  }

  if (dataset.ground_truth.empty()) {
    computeGroundTruth(dataset);
  }

  if (!config_.save_data_dir.empty()) {
    saveData(dataset);
  }

  return dataset;
}

void DatasetBuilder::generateData(BenchmarkDataset& dataset) {
  std::mt19937 rng(config_.seed);
  std::normal_distribution<float> dist(0.0f, 1.0f);

  dataset.base.resize(static_cast<std::size_t>(dataset.nb) * dataset.dim);
  dataset.queries.resize(static_cast<std::size_t>(dataset.nq) * dataset.dim);

  for (auto& v : dataset.base) {
    v = dist(rng);
  }
  for (auto& v : dataset.queries) {
    v = dist(rng);
  }

  if (config_.normalize) {
    normalize(dataset.base.data(), dataset.nb, dataset.dim);
    normalize(dataset.queries.data(), dataset.nq, dataset.dim);
  }
}

void DatasetBuilder::normalize(float* vectors, int n, int d) {
  for (int i = 0; i < n; ++i) {
    double norm = 0.0;
    float* row = vectors + static_cast<std::size_t>(i) * d;
    for (int j = 0; j < d; ++j) {
      norm += static_cast<double>(row[j]) * static_cast<double>(row[j]);
    }
    norm = std::sqrt(norm);
    if (norm > 0.0) {
      for (int j = 0; j < d; ++j) {
        row[j] = static_cast<float>(row[j] / norm);
      }
    }
  }
}

void DatasetBuilder::loadData(BenchmarkDataset& dataset) {
  const auto base_file = config_.load_data_dir + "/database_" + std::to_string(dataset.dim) + "d_" + std::to_string(dataset.nb) + "n.fvecs";
  const auto query_file = config_.load_data_dir + "/queries_" + std::to_string(dataset.dim) + "d_" + std::to_string(dataset.nq) + "n.fvecs";
  const auto gt_file = config_.load_data_dir + "/groundtruth_" + std::to_string(dataset.nq) + "q_" + std::to_string(dataset.k) + "k.ivecs";

  if (!fileExists(base_file) || !fileExists(query_file) || !fileExists(gt_file)) {
    return;
  }

  if (!loadFVecs(base_file, dataset.base, dataset.nb, dataset.dim)) {
    dataset.base.clear();
  }
  if (!loadFVecs(query_file, dataset.queries, dataset.nq, dataset.dim)) {
    dataset.queries.clear();
  }
  if (!loadIVecs(gt_file, dataset.ground_truth, dataset.nq, dataset.k)) {
    dataset.ground_truth.clear();
  }
}

void DatasetBuilder::saveData(const BenchmarkDataset& dataset) const {
  const auto base_file = config_.save_data_dir + "/database_" + std::to_string(dataset.dim) + "d_" + std::to_string(dataset.nb) + "n.fvecs";
  const auto query_file = config_.save_data_dir + "/queries_" + std::to_string(dataset.dim) + "d_" + std::to_string(dataset.nq) + "n.fvecs";
  const auto gt_file = config_.save_data_dir + "/groundtruth_" + std::to_string(dataset.nq) + "q_" + std::to_string(dataset.k) + "k.ivecs";

  saveFVecs(base_file, dataset.base, dataset.nb, dataset.dim);
  saveFVecs(query_file, dataset.queries, dataset.nq, dataset.dim);
  saveIVecs(gt_file, dataset.ground_truth, dataset.nq, dataset.k);
}

void DatasetBuilder::computeGroundTruth(BenchmarkDataset& dataset) {
  const int dim = dataset.dim;
  const int64_t nb = dataset.nb;
  const int nq = dataset.nq;
  const int k = dataset.k;
  dataset.ground_truth.resize(static_cast<std::size_t>(nq) * k);

  const float* base_ptr = dataset.base.data();
  const float* query_ptr = dataset.queries.data();

  std::vector<std::pair<float, std::int64_t>> distances;
  distances.reserve(static_cast<std::size_t>(nb));

  for (int qi = 0; qi < nq; ++qi) {
    distances.clear();
    const float* current_query = query_ptr + static_cast<std::size_t>(qi) * dim;
    for (int64_t bi = 0; bi < nb; ++bi) {
      const float* current_base = base_ptr + static_cast<std::size_t>(bi) * dim;
      float dist = 0.0f;
      for (int d = 0; d < dim; ++d) {
        const float diff = current_query[d] - current_base[d];
        dist += diff * diff;
      }
      distances.emplace_back(dist, bi);
    }

    const std::size_t top = static_cast<std::size_t>(std::min(k, static_cast<int>(distances.size())));
    std::partial_sort(distances.begin(), distances.begin() + top, distances.end(),
                      [](const auto& lhs, const auto& rhs) { return lhs.first < rhs.first; });
    for (int i = 0; i < k; ++i) {
      std::int64_t id = i < static_cast<int>(distances.size()) ? distances[static_cast<std::size_t>(i)].second : -1;
      dataset.ground_truth[static_cast<std::size_t>(qi) * k + i] = id;
    }
  }
}

bool DatasetBuilder::fileExists(const std::string& path) {
  std::ifstream ifs(path, std::ios::binary);
  return ifs.good();
}

bool DatasetBuilder::loadFVecs(const std::string& path, std::vector<float>& data, int expected_n, int expected_d) {
  std::ifstream file(path, std::ios::binary);
  if (!file.is_open()) {
    return false;
  }

  data.resize(static_cast<std::size_t>(expected_n) * expected_d);
  for (int i = 0; i < expected_n; ++i) {
    int d = 0;
    file.read(reinterpret_cast<char*>(&d), sizeof(int));
    if (file.fail() || d != expected_d) {
      return false;
    }
    file.read(reinterpret_cast<char*>(data.data() + static_cast<std::size_t>(i) * expected_d), expected_d * sizeof(float));
    if (file.fail()) {
      return false;
    }
  }
  return true;
}

bool DatasetBuilder::loadIVecs(const std::string& path, std::vector<std::int64_t>& data, int expected_n, int expected_d) {
  std::ifstream file(path, std::ios::binary);
  if (!file.is_open()) {
    return false;
  }

  data.resize(static_cast<std::size_t>(expected_n) * expected_d);
  for (int i = 0; i < expected_n; ++i) {
    int d = 0;
    file.read(reinterpret_cast<char*>(&d), sizeof(int));
    if (file.fail() || d != expected_d) {
      return false;
    }
    for (int j = 0; j < expected_d; ++j) {
      int val = 0;
      file.read(reinterpret_cast<char*>(&val), sizeof(int));
      if (file.fail()) {
        return false;
      }
      data[static_cast<std::size_t>(i) * expected_d + j] = static_cast<std::int64_t>(val);
    }
  }
  return true;
}

void DatasetBuilder::saveFVecs(const std::string& path, const std::vector<float>& data, int n, int d) {
  std::ofstream file(path, std::ios::binary);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open " + path + " for writing");
  }

  for (int i = 0; i < n; ++i) {
    file.write(reinterpret_cast<const char*>(&d), sizeof(int));
    file.write(reinterpret_cast<const char*>(data.data() + static_cast<std::size_t>(i) * d), d * sizeof(float));
  }
}

void DatasetBuilder::saveIVecs(const std::string& path, const std::vector<std::int64_t>& data, int n, int d) {
  std::ofstream file(path, std::ios::binary);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open " + path + " for writing");
  }

  for (int i = 0; i < n; ++i) {
    file.write(reinterpret_cast<const char*>(&d), sizeof(int));
    for (int j = 0; j < d; ++j) {
      int value = static_cast<int>(data[static_cast<std::size_t>(i) * d + j]);
      file.write(reinterpret_cast<const char*>(&value), sizeof(int));
    }
  }
}

} // namespace vecbench
