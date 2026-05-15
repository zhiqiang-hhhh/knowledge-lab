#pragma once

#include "benchmark_config.h"

#include <string>

namespace vecbench {

BenchmarkConfig parseCommandLine(int argc, char** argv);
void printHelp(const std::string& binary_name);

} // namespace vecbench
