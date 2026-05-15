class Solution {
 public:
  vector<int> majorityElement(vector<int>& nums) {
    size_t count1 = 0, count2 = 0;
    int result1 = INT32_MIN, result2 = INT32_MIN;
    vector<int> res;

    for (const auto& i : nums) {
      if (i == result1)
        count1++;
      else if (i == result2)
        count2++;
      else if (count1 == 0) {
        result1 = i;
        count1++;
      } else if (count2 == 0) {
        result2 = i;
        count2++;
      } else {
        count1--;
        count2--;
      }
    }

    count1 = count2 = 0;
    for (const auto& i : nums) {
      if (i == result1)
        count1++;
      else if (i == result2)
        count2++;
    }

    if (count1 > nums.size() / 3) res.push_back(result1);
    if (count2 > nums.size() / 3) res.push_back(result2);

    return res;
  }
};