#include "results_utils.h"
#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <sys/stat.h>

namespace results_utils {

bool csvFileExists(const std::string &path) {
  std::ifstream in(path);
  return in.good();
}

std::ofstream openCsvAppend(const std::string &path, bool &existed) {
  existed = csvFileExists(path);
  std::ofstream out;
  if (existed)
    out.open(path, std::ios::app);
  else
    out.open(path, std::ios::out);
  return out;
}

std::string currentRunTimeString() {
  auto now = std::chrono::system_clock::now();
  std::time_t t = std::chrono::system_clock::to_time_t(now);
  std::tm tm = *std::localtime(&t);
  std::ostringstream ts;
  ts << std::put_time(&tm, "%Y-%m-%d %H:%M:%S");
  return ts.str();
}

} // namespace results_utils
