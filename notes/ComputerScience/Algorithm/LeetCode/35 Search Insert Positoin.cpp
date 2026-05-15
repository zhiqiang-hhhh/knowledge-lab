class Solution {
 public:
  int searchInsert(vector<int>& nums, int target) {
    if (nums.size() == 0) return 0;
    int start = 0, end = nums.size() - 1;

    // 区间左“移”
    while (start + 1 < end) {
      auto mid = start + (end - start) / 2;
      if (nums[mid] >= target)
        end = mid;
      else
        start = mid;
    }

    if (nums[start] >= target) return start;

    if (nums[end] >= target) return end;

    return end + 1;
  }
};