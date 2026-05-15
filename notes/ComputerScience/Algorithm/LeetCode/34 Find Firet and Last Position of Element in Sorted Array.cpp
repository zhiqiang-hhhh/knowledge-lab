class Solution {
 public:
  vector<int> searchRange(vector<int>& nums, int target) {
    vector<int> res(2, -1);
    if (nums.empty()) return res;

    auto end = nums.size() - 1;
    decltype(end) start = 0;

    // 使用二分法通用模板
    // 使用整数索引
    // 先找 lower bound
    while (start + 1 < end) {
      auto mid = start + (end - start) / 2;
      // 优先移动 end
      if (nums.at(mid) >= target)
        end = mid;
      else
        start = mid;
    }
    // 注意顺序
    if (nums.at(end) == target) res[0] = end;
    if (nums.at(start) == target) res[0] = start;

    if (res[0] == -1) return res;

    // 不需要移动 start
    end = nums.size() - 1;
    // 寻找 upper bound
    while (start + 1 < end) {
      auto mid = start + (end - start) - 1;
      // 优先移动 start
      if (nums.at(mid) <= target)
        start = mid;
      else
        end = mid;
    }
    // 注意顺序，与之前相反
    if (nums.at(start) == target) res[1] = start;
    if (nums.at(end) == target) res[1] = end;

    return res;
  }
};
