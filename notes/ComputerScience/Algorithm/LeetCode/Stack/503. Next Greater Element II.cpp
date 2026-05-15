class Solution {
 public:
  vector<int> nextGreaterElements(vector<int>& nums) {
    stack<int> stk;
    vector<int> nges(nums.size(), -1);

    int j = 0, i;
    while (j < 2 * (nums.size())) {
      i = j % nums.size();
      if (stk.empty() || nums[i] <= nums[stk.top()]) {
        stk.push(i);
        j++;
      } else {
        nges[stk.top()] = i;
        stk.pop();
      }
    }
    for (auto& num : nges) {
      num = (num == -1) ? -1 : nums[num];
    }
    return nges;
  }
};