class Solution {
 public:
  string longestPalindrome(string s) {
    if (s.size() <= 1) return s;

    int len = s.size(), lpsStart = 0, lpsLength = 1;
    bool memo[len][len];

    for (int i = 0; i < len; i++) {
      memo[i][i] = true;
    }

    for (int start = len - 1; start >= 0; start--) {
      for (int distance = 1; distance < len - start; distance++) {
        int end = start + distance;
        memo[start][end] = (distance == 1) ? (s[start] == s[end])
                                           : ((s[start] == s[end]) &&
                                              (memo[start + 1][end - 1]));
        if (memo[start][end] && distance + 1 > lpsLength) {
          lpsStart = start;
          lpsLength = distance + 1;
        }
      }
    }

    return s.substr(lpsStart, lpsLength);
  }
};