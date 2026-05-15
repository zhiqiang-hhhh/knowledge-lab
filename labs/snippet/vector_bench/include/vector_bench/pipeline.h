#pragma once

#include "benchmark_config.h"
#include "metrics.h"

namespace vecbench {

class BenchmarkPipeline {
public:
  explicit BenchmarkPipeline(BenchmarkConfig config);

  BenchmarkResults run();

private:
  BenchmarkConfig config_;
};

} // namespace vecbench
