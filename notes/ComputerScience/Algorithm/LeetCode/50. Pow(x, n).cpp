class Solution {
 public:
  double myPow(double x, int n) {
    if (n == INT32_MIN)
    // x - 1 == INT32_MAX
    // INT32_MAX = 2147483647
    // INT32_MIN = -2147483648
    {
      std::cout << n << std::endl;
      std::cout << -(n + 1) << std::endl;
      return myPow(1 / x, -(n + 1)) / x;
    }

    if (n < 0) return myPow(1 / x, -n);

    double ans = 1;
    while (n) {
      // 考虑 n 的二进制表示
      // 若当前最低位为 1，则进行一次 anx *= x
      if (n & 1 == 1) ans *= x;
      x *= x;
      n >>= 1;
    }
    return ans;
  }
};