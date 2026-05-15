class Solution {
 public:
  int myAtoi(string str) {
    if (str.size() == 0) return 0;
    int indicator = 1;
    __int64_t result = 0;

    int i = str.find_first_not_of(' ');
    if (i >= str.size()) return 0;
    if (str[i] == '+' || str[i] == '-') {
      indicator = (str[i++] == '-') ? -1 : 1;
    }

    while (i < str.size() && str[i] >= '0' && str[i] <= '9') {
      result = result * 10 + str[i++] - '0';
      if (result * indicator >= INT32_MAX) return INT32_MAX;
      if (result * indicator <= INT32_MIN) return INT32_MIN;
    }
    return result * indicator;
  }
};