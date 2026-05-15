#include "cli_utils.h"
#include <sstream>
#include <string>
#include <faiss/IndexScalarQuantizer.h>

std::vector<std::string> splitCSV(const std::string &s) {
  std::vector<std::string> out;
  std::stringstream ss(s);
  std::string item;
  while (std::getline(ss, item, ',')) {
    if (!item.empty())
      out.push_back(item);
  }
  return out;
}

std::vector<int> toIntList(const std::string &s) {
  std::vector<int> v;
  auto parts = splitCSV(s);
  v.reserve(parts.size());
  for (auto &p : parts) {
    try {
      v.push_back(std::stoi(p));
    } catch (...) {
    }
  }
  return v;
}

std::vector<double> toDoubleList(const std::string &s) {
  std::vector<double> v;
  auto parts = splitCSV(s);
  v.reserve(parts.size());
  for (auto &p : parts) {
    try {
      v.push_back(std::stod(p));
    } catch (...) {
    }
  }
  return v;
}

int parseQType(const std::string &s) {
  using QT = faiss::ScalarQuantizer::QuantizerType;
  if (s == "QT_8bit")
    return (int)QT::QT_8bit;
  if (s == "QT_4bit")
    return (int)QT::QT_4bit;
  if (s == "QT_8bit_uniform")
    return (int)QT::QT_8bit_uniform;
  if (s == "QT_fp16")
    return (int)QT::QT_fp16;
  // fallback: try int
  try {
    return std::stoi(s);
  } catch (...) {
    return (int)QT::QT_8bit;
  }
}
