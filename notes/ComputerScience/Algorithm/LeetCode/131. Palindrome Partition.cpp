class Solution {
 public:
  vector<vector<string>> partition(string s) {
    vector<bool> temp(s.size(), false);
    vector<vector<bool>> memo(s.size(), temp);

    for (int i = 0; i < s.size(); i++) {
      memo[i][i] = true;
    }

    for (int i = 0; i < s.size(); i++) {
      for (int j = 0; j < i; j++) {
        if (s[i] != s[j])
          continue;
        else if (j + 1 == i) {
          memo[j][i] = true;
        } else if (memo[j + 1][i - 1] == true) {
          memo[j][i] = true;
        } else {
          continue;
        }
      }
    }

    vector<vector<string>> res;
    vector<string> path;
    helper(res, path, s, memo, 0);
    return res;
  }
  // DFS，
  void helper(vector<vector<string>>& res, vector<string> path, const string& s,
              const vector<vector<bool>>& memo, int pos) {
    if (pos >= memo.size()) {
      res.push_back(path);
      return;
    }
    for (int i = pos; i < memo.size(); i++) {
      if (memo[pos][i] == true) {
        vector<string> temp = path;
        temp.push_back(s.substr(pos, i - pos + 1));
        helper(res, temp, s, memo, i + 1);
      }
    }
  }
};