#pragma once
#include <string>
#include <vector>

std::vector<std::string> splitCSV(const std::string &s);
std::vector<int> toIntList(const std::string &s);
std::vector<double> toDoubleList(const std::string &s);
int parseQType(const std::string &s);
