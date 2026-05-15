class Solution {
 public:
  int missingNumber(vector<int>& nums) {
    int ret = nums.size();
    int i = 0;

    for (auto& num : nums) {
      ret ^= num;  // 按位异或
      ret ^= i;
      i++;
    }

    return ret;
  }
};