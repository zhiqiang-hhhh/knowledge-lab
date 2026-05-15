#pragma once

#include "vector_library.h"

namespace vecbench {

class FaissLibrary : public VectorLibrary {
public:
  FaissLibrary();
  ~FaissLibrary() override;

  std::string name() const override;
  void initialize(const BenchmarkConfig& config) override;
  void prepareDataset(BenchmarkDataset& dataset) override;
  std::unique_ptr<AlgorithmRunner> createRunner(const AlgorithmSpec& spec) override;

private:
  bool initialized_ = false;
};

std::unique_ptr<VectorLibrary> makeFaissLibrary();

} // namespace vecbench
