class Solution {
 public:
  vector<int> maxSlidingWindow(vector<int>& nums, int k) {
    if (nums.empty()) return vector<int>();
    deque<int> window;
    vector<int> res;
    for (int i = 0; i < nums.size(); i++) {
      if (!window.empty() && window.front() == i - k) window.pop_front();
      // 把 window 中所有小于新加入元素的值都干掉
      while (!window.empty() && nums[window.back()] < nums[i]) {
        window.pop_back();
      }
      window.push_back(i);
      if (i >= k - 1) res.push_back(nums[window.front()]);
    }
    return res;
  }
};