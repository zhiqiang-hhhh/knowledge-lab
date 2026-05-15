class Solution {
 public:
  int maxProduct(vector<int>& nums) {
    if (nums.empty()) return 0;

    int ret = INT_MIN;
    int maxProd = 1;
    int minProd = 1;

    for (int i = 0; i < nums.size(); ++i) {
      if (nums[i] < 0) swap(minProd, maxProd);

      maxProd = max(maxProd * nums[i], nums[i]);
      minProd = min(minProd * nums[i], nums[i]);

      ret = max(maxProd, ret);
    }
    return ret;
  }
};