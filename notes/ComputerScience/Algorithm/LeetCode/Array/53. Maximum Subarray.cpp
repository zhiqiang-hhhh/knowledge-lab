class Solution {
 public:
  int maxSubArray(vector<int>& nums) {
    vector<int> prefixSum{0};

    for (int i = 0; i < nums.size(); ++i)
      prefixSum.push_back(nums[i] + prefixSum[i]);

    int maxSubArray = INT32_MIN;
    for (int i = 1; i < prefixSum.size(); ++i) {
      for (int j = 0; j < i; ++j) {
        maxSubArray = max(maxSubArray, prefixSum[i] - prefixSum[j]);
      }
    }
    return maxSubArray;
  }
};