class Solution {
 public:
  int mySqrt(int x) {
    if (x == 0) return 0;
    int left = 1, right = x;
    while (left + 1 < right) {
      int mid = left + (right - left) / 2;
      // if((mid * mid) == x) 会整数溢出
      if (mid == (x / mid)) {
        return mid;
      } else if (mid > (x / mid)) {
        right = mid;
      } else {
        left = mid;
      }
    }  // while
    if ((left * left) <= x) {
      return left;
    }
    return right;
  }
};