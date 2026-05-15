class Solution {
 public:
  vector<vector<int>> fourSum(vector<int>& nums, int target) {
    std::sort(nums.begin(), nums.end) vector<vector<int>> res;

    for (int a = 0; a <= (int)nums.size() - 4; a++) {
      if (a >= 1 && nums[a] == nums[a - 1]) continue;

      for (int b = a + 1; b <= (int)nums.size() - 3; b++) {
        if (b >= a + 2 && nums[b] == nums[b - 1]) continue;

        int c = b + 1, d = nums.size() - 1;
        int subTarget = target - nums[a] - nums[b];
        while (c < d) {
          int sum = nums[c] + nums[d];
          if (sum < subTarget)
            c++;
          else if (sum > subTarget)
            d--;
          else {
            vector<int> temp{nums[a], nums[b], nums[c++], nums[d--]};
            res.push_back(temp);

            while (c < d && nums[c] == nums[c - 1]) c++;
            while (c < d && nums[d] == nums[d + 1]) d--;
          }
        }
      }
    }
    return res;
  }
};