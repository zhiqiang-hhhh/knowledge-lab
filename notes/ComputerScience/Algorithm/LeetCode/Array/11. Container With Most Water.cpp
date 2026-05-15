class Solution {
 public:
  int maxArea(vector<int>& height) {
    int ret = 0;
    int _width, _height;

    if (height.size() <= 1) return ret;

    auto left = height.begin(), right = height.end() - 1;
    while (left < right) {
      _width = right - left;
      _height = min(*left, *right);

      ret = max(ret, _width * _height);

      if (*left >= *right)
        right--;
      else
        left++;
    }
    return ret;
  }
};