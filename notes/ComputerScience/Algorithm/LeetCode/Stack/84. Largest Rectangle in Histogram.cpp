class Solution {
 public:
  int largestRectangleArea(vector<int>& heights) {
    if (heights.empty()) return 0;

    stack<int> stk;
    int curPos = 0;
    int maxArea = INT_MIN;

    while (curPos < heights.size()) {
      if (stk.empty() || heights[curPos] >= heights[stk.top()])
        stk.push(curPos++);
      else {
        // curHeight > stk.top
        // 如果我们以heights[stk.top]作为最低bar
        // 那么 curPos 就是 right index
        // stk.top 下的第一个元素就是 left index
        int botPos = stk.top();
        stk.pop();

        int leftPos = stk.empty() ? -1 : stk.top();
        int tmpArea = heights[botPos] * (curPos - leftPos - 1);
        maxArea = max(maxArea, tmpArea);
      }
    }

    while (!stk.empty()) {
      int botPos = stk.top();
      stk.pop();

      int leftPos = stk.empty() ? -1 : stk.top();
      int tmpArea = heights[botPos] * (curPos - leftPos - 1);
      maxArea = max(maxArea, tmpArea);
    }
    return maxArea;
  }
};