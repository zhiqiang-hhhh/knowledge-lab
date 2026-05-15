// Small helpers for CSV result appending and timestamps
#pragma once
#include <fstream>
#include <string>

namespace results_utils {

bool csvFileExists(const std::string &path);

// Open CSV in append mode. 'existed' will be set to true if file already
// existed. Caller receives an opened ofstream (may be in bad state if open
// failed).
std::ofstream openCsvAppend(const std::string &path, bool &existed);

// Return a human-readable timestamp for run_time column: "YYYY-MM-DD HH:MM:SS"
std::string currentRunTimeString();

} // namespace results_utils
