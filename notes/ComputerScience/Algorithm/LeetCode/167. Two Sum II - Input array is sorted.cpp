class Solution {
 public:
  vector<int> twoSum(vector<int>& numbers, int target) {
    vector<int> res;

    int a = 0, b = (int)numbers.size() - 1;

    while (a < b) {
      int sum = numbers[a] + numbers[b];
      if (sum < target)
        a++;
      else if (sum > target)
        b--;
      else {
        res.push_back(++a);
        res.push_back(++b);
        break;
      }
    }
    return res;
  }
};