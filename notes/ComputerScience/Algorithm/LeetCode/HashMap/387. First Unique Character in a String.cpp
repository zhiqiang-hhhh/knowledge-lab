class Solution {
 public:
  int firstUniqChar(string s) {
    unordered_map<char, pair<int, int>> cnt;
    for (int i = 0; i < s.size(); ++i) {
      cnt[s[i]].first++;
      cnt[s[i]].second = i;
    }
    int ret = s.size();
    for (auto& kv : cnt) {
      if (kv.second.first == 1) {
        ret = min(ret, kv.second.second);
      }
    }
    return ret == s.size() ? -1 : ret;
  }
};