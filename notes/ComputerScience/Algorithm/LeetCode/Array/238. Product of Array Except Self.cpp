class Solution {
 public:
  vector<int> productExceptSelf(vector<int>& nums) {
    int leftProd = 1;
    int rightProd = 1;
    vector<int> ret(nums.size(), 1);

    for (int i = 0; i < nums.size(); ++i) {
      ret[i] *= leftProd;
      leftProd *= nums[i];
      ret[nums.size() - 1 - i] *= rightProd;
      rightProd *= nums[nums.size() - 1 - i];
    }

    return ret;
  }
};