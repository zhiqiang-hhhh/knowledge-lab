/**
 * // This is the interface that allows for creating nested lists.
 * // You should not implement it, or speculate about its implementation
 * class NestedInteger {
 *   public:
 *     // Constructor initializes an empty nested list.
 *     NestedInteger();
 *
 *     // Constructor initializes a single integer.
 *     NestedInteger(int value);
 *
 *     // Return true if this NestedInteger holds a single integer, rather than
 * a nested list. bool isInteger() const;
 *
 *     // Return the single integer that this NestedInteger holds, if it holds a
 * single integer
 *     // The result is undefined if this NestedInteger holds a nested list
 *     int getInteger() const;
 *
 *     // Set this NestedInteger to hold a single integer.
 *     void setInteger(int value);
 *
 *     // Set this NestedInteger to hold a nested list and adds a nested integer
 * to it. void add(const NestedInteger &ni);
 *
 *     // Return the nested list that this NestedInteger holds, if it holds a
 * nested list
 *     // The result is undefined if this NestedInteger holds a single integer
 *     const vector<NestedInteger> &getList() const;
 * };
 */

class Solution {
 public:
  NestedInteger deserialize(string s) {
    stack<NestedInteger> stk;
    auto isDigit = [](const char& c) { return (c == '-') || isdigit(c); };

    if (isDigit(s.front())) {
      return stoi(string(s.begin(), s.end()));
    }

    auto itr = s.begin();
    while (itr < s.end()) {
      if (isDigit(*itr)) {
        auto valueEnd = find_if_not(itr, s.end(), isDigit);
        if (stk.empty())  // 用于处理输入为单个整数的情况，这种情况下没有[]
          stk.push(NestedInteger(stoi(string(itr, valueEnd))));
        else
          stk.top().add(stoi(string(itr, valueEnd)));

        itr = valueEnd;
      } else {
        if (*itr == '[') {
          stk.push(NestedInteger());
        } else if (*itr == ']') {
          NestedInteger ni = stk.top();
          stk.pop();
          if (stk.empty())  // 用于处理输入为[]的情况
            stk.push(ni);
          else
            stk.top().add(ni);
        }
        ++itr;
      }
    }
    return stk.top();
  }
};

/*=======递归解法=======*/
class Solution {
  NestedInteger parse(string& s, int& pos) {
    if (s[pos] == '[') return parseNestedList(s, pos);
    return parseInteger(s, pos);
  }

  NestedInteger parseInteger(string& s, int& pos) {
    int sign = s[pos] == '-' ? -1 : 1;
    if (s[pos] == '+' || s[pos] == '-') ++pos;
    int num = 0;
    while (isdigit(s[pos])) {
      num = num * 10 + s[pos++] - '0';
    }
    num *= sign;
    return NestedInteger(num);
  }

  NestedInteger parseNestedList(string& s, int& pos) {
    NestedInteger ni;
    // pos++;
    while (s[pos] != ']') {
      pos++;  // skip , and first [
      if (s[pos] == ']') break;
      ni.add(parse(s, pos));
    }
    pos++;
    return ni;
  }

 public:
  NestedInteger deserialize(string s) {
    int pos = 0;
    return parse(s, pos);
  }
};