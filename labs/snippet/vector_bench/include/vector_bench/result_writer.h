#pragma once

#include "metrics.h"

#include <ostream>

namespace vecbench {

class ResultWriter {
public:
  explicit ResultWriter(const OutputConfig& config);

  void writeCsv(const BenchmarkResults& results) const;
  void printSummary(const BenchmarkResults& results, std::ostream& os) const;

private:
  OutputConfig config_;
};

} // namespace vecbench
