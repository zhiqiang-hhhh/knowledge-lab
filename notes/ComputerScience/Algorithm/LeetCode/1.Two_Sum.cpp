class Solution {
 public:
  vector<int> twoSum(vector<int>& nums, int target) {
    vector<int> res;
    unordered_map<int, int> hm;

    for (int i = 0; i < nums.size(); i++) {
      auto t = hm.find(target - nums[i]);
      if (t != hm.end()) {
        res.push_back(i);
        res.push_back(t->second);
        break;
      }
      // 防止重复
      hm[nums[i]] = i;
    }
    return res;
  };