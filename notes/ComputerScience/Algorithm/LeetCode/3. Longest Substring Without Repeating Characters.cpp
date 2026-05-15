class Solution {
 public:
  int lengthOfLongestSubstring(string s) {
    if (s.size() == 0) return 0;

    unordered_map<char, size_t> charMap;
    vector<size_t> memo(s.size());

    charMap[s[0]] == 0;
    memo[0] = 1;

    for (int i = 1; i < s.size(); i++) {
      if (charMap.count(s[i]) == 0) {
        charMap[s[i]] = i;
        memo[i] = memo[i - 1] + 1;
      } else if (charMap[s[i]] + memo[i - 1] >= i) {
        auto old = charMap[s[i]];
        charMap[s[i]] = i;
        memo[i] = i - old;
      } else {
        charMap[s[i]] = i;
        memo[i] = memo[i - 1] + 1;
      }
    }

    size_t l = 1;
    for (auto& i : memo) {
      l = max(i, l);
    }
    return (int)l;
  }
};