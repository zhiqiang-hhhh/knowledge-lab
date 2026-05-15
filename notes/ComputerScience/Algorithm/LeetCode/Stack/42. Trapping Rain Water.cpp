class Solution {
 public:
  int trap(vector<int>& height) {
    if (height.size() <= 2) return 0;

    stack<int> stk;
    int ret = 0;
    int cur = 0;
    while (cur < height.size()) {
      if (stk.empty() || height[cur] <= height[stk.top()])
        stk.push(cur++);
      else {
        // stk.top() 保存的是 bot 的位置
        int botPos = stk.top();
        // 当最底层装过水以后，最底层已经不再是最底层，所以需要pop
        stk.pop();
        if (!stk.empty()) {
          // 此时stk.top()保存可用的最低左边挡板位置
          int validHeight = min(height[cur], height[stk.top()]);
          // 添加新增水域面积
          // 这里的新增水域面积是以最低左边挡板计算的
          ret += (validHeight - height[botPos]) * (cur - stk.top() - 1);
        }
        // 由于左边挡板有可能有多个
        // 所以cur不能移动
        // cur可能还需要和次最低左边挡板计算面积执行第15行
        // 或者cur成为新bot，执行第12行
      }
    }
    return ret;
  }
};