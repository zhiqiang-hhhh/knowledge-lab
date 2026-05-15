class Solution {
 public:
  void sortColors(vector<int>& nums) {
    int c0 = -1, c1 = -1, c2 = -1;
    for (auto i : nums) {
      if (i == 0) {
        nums[++c2] = 2;
        nums[++c1] = 1;
        nums[++c0] = 0;
      } else if (i == 1) {
        nums[++c2] = 2;
        nums[++c1] = 1;
      } else if (i == 2) {
        nums[++c2] = 2;
      }
    }
  }
};