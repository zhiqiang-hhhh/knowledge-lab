class Solution {
 public:
  vector<vector<int>> threeSum(vector<int>& nums) {
    sort(nums.begin(), nums.end());
    vector<vector<int>> res;

    for (int a = 0; a <= (int)nums.size() - 3; a++) {
      // 过滤重复
      if ((a >= 1) && nums[a] == nums[a - 1]) continue;

      // 双指针
      int b = a + 1, c = nums.size() - 1;

      while (b < c) {
        if (nums[a] + nums[b] + nums[c] < 0) {
          b++;
        } else if (nums[a] + nums[b] + nums[c] > 0) {
          c--;
        } else {
          vector<int> temp{nums[a], nums[b++], nums[c--]};
          res.push_back(temp);
          // 过滤重复
          while (b < c && nums[b] == nums[b - 1]) b++;
          // 过滤重复
          while (b < c && nums[c] == nums[c + 1]) c--;
        }
      }
    }

    return res;
  }
};