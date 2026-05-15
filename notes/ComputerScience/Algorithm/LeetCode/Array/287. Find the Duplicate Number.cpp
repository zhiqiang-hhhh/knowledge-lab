class Solution {
 public:
  int findDuplicate(vector<int>& nums) {
    int left = 1, right = nums.size();

    while (left < right) {
      auto mid = left + ((right - left) >> 1);
      int count = calCount(nums, left, mid);
      // cout << mid << ' ' << count << endl;
      if (count > mid - left + 1) {
        right = mid;
      } else {
        left = mid + 1;
      }
    }
    return left;
  }
  int calCount(const vector<int>& nums, int left, int right) {
    int cnt = 0;
    for (auto& num : nums) {
      if (left <= num && num <= right) ++cnt;
    }
    return cnt;
  }
};