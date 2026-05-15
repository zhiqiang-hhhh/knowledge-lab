class Solution {
 public:
  vector<int> nextGreaterElement(vector<int>& nums1, vector<int>& nums2) {
    unordered_map<int, int> hashMap;
    stack<int> stk;

    int i = 0;
    while (i < nums2.size()) {
      if (stk.empty() || nums2[i] <= stk.top())
        stk.push(nums2[i++]);
      else {
        hashMap[stk.top()] = nums2[i];
        stk.pop();
      }
    }

    vector<int> ret;
    for (const auto& num : nums1) {
      if (hashMap.find(num) != hashMap.end())
        ret.push_back(hashMap[num]);
      else {
        ret.push_back(-1);
      }
    }
    return ret;
  }
};