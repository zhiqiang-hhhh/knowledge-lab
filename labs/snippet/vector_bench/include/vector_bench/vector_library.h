#pragma once

#include "benchmark_config.h"
#include "dataset.h"
#include "metrics.h"

#include <memory>
namespace vecbench {

struct BenchmarkContext;

class AlgorithmRunner {
public:
  virtual ~AlgorithmRunner() = default;
  virtual BenchmarkResult run(const BenchmarkContext& ctx,
                              const AlgorithmSpec& spec) = 0;
};

class VectorLibrary {
public:
  virtual ~VectorLibrary() = default;
  virtual std::string name() const = 0;
  virtual void initialize(const BenchmarkConfig& config) = 0;
  virtual void prepareDataset(BenchmarkDataset& dataset) = 0;
  virtual std::unique_ptr<AlgorithmRunner> createRunner(const AlgorithmSpec& spec) = 0;
};

struct BenchmarkContext {
  BenchmarkConfig config;
  BenchmarkDataset dataset;
};

} // namespace vecbench
