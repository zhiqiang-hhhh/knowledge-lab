class Solution {
 public:
  string removeDuplicateLetters(string s) {
    vector<int> charCount(26, 0);     // 统计string中字符的剩余数量
    vector<bool> visited(26, false);  // 记录stack中是否存在某个字符
    stack<char> stk;

    for (auto& c : s) {
      charCount[c - 'a']++;
    }

    for (auto& c : s) {
      charCount[c - 'a']--;
      if (visited[c - 'a'])  // c 为旧字符
        continue;

      while (!stk.empty() && c <= stk.top() && charCount[stk.top() - 'a']) {
        visited[stk.top() - 'a'] = false;
        stk.pop();
      }

      visited[c - 'a'] = true;
      stk.push(c);
    }

    string ret;
    while (!stk.empty()) {
      ret = stk.top() + ret;
      stk.pop();
    }
    return ret;
  }
};