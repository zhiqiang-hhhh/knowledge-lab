/**
 * // This is the interface that allows for creating nested lists.
 * // You should not implement it, or speculate about its implementation
 * class NestedInteger {
 *   public:
 *     // Return true if this NestedInteger holds a single integer, rather than
 * a nested list. bool isInteger() const;
 *
 *     // Return the single integer that this NestedInteger holds, if it holds a
 * single integer
 *     // The result is undefined if this NestedInteger holds a nested list
 *     int getInteger() const;
 *
 *     // Return the nested list that this NestedInteger holds, if it holds a
 * nested list
 *     // The result is undefined if this NestedInteger holds a single integer
 *     const vector<NestedInteger> &getList() const;
 * };
 */
// ?????
class NestedIterator {
 public:
  NestedIterator(vector<NestedInteger>& nestedList) {
    if (nestedList.empty())  // process []
      return;

    for (auto i = nestedList.end() - 1; i >= nestedList.begin(); --i)
      stk.push(i);
  }

  int next() {
    int ret = stk.top()->getInteger();
    stk.pop();
    return ret;
  }

  bool hasNext() {
    while (!stk.empty()) {
      if (stk.top()->isInteger()) return true;

      // stk.top() is not a single Integer
      // maybe another NestedInteger，or a []
      // need flatten
      auto& vNI = stk.top()->getList();
      stk.pop();
      if (vNI.empty())  // precess []
        continue;

      for (auto i = vNI.end() - 1; i >= vNI.begin(); --i) stk.push(i);
    }
    return false;
  }

 private:
  stack<vector<NestedInteger>::iterator> stk;
};

/**
 * Your NestedIterator object will be instantiated and called as such:
 * NestedIterator i(nestedList);
 * while (i.hasNext()) cout << i.next();
 */