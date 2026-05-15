class Solution {
 public:
  int majorityElement(vector<int>& nums) {
    size_t count = 0;
    int result = INT_MIN;
    for (const auto& i : nums) {
      if (result == i)
        count++;
      else if (count == 0) {
        count++;
        result = i;
      } else {
        count--;
      }
    }
    return result;
  }
};