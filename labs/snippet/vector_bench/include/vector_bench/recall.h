#pragma once

#include <cstdint>
#include <vector>

namespace vecbench {

double recallAtK(const std::vector<std::int64_t>& predicted,
                 const std::vector<std::int64_t>& truth,
                 int nq, int k, int top_k);

} // namespace vecbench
