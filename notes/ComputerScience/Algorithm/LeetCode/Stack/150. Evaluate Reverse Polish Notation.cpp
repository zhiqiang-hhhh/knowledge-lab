class Solution {
 public:
  int evalRPN(vector<string>& tokens) {
    stack<int> stk;
    for (const auto& s : tokens) {
      if (isdigit(s.back())) {
        stk.push(stoi(s));
      } else {
        int rhs = stk.top();
        stk.pop();
        int lhs = stk.top();
        stk.pop();
        int ans;
        if (s == "+") {
          ans = lhs + rhs;
        } else if (s == "-") {
          ans = lhs - rhs;
        } else if (s == "*") {
          ans = lhs * rhs;
        } else {
          ans = lhs / rhs;
        }
        stk.push(ans);
      }
    }
    return stk.top();
  }
};

class Solution {
 public:
  int evalRPN(vector<string>& tokens) {
    const string& s = tokens.back();
    tokens.pop_back();
    if (s != "+" && s != "-" && s != "*" && s != "/") return stoi(s);

    int rhs = evalRPN(tokens), lhs = evalRPN(tokens);
    int ans;

    if (s == "+")
      ans = lhs + rhs;
    else if (s == "-")
      ans = lhs - rhs;
    else if (s == "*")
      ans = lhs * rhs;
    else
      ans = lhs / rhs;

    return ans;
  }
};