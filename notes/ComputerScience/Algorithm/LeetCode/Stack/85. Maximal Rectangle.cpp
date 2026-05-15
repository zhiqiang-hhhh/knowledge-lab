class Solution {
 public:
  int maximalRectangle(vector<vector<char>>& matrix) {
    if (matrix.size() == 0) return 0;

    int maxArea = 0;

    int rowSize = matrix.size();
    int colSize = matrix[0].size();
    vector<vector<int>> histograms(rowSize, vector<int>(colSize, 0));

    for (int row = 0; row < rowSize; ++row) {
      // 计算每一行的直方图
      for (int col = 0; col < colSize; ++col) {
        int i = row, j = col;
        while (i < rowSize && matrix[i][j] == '1') {
          histograms[row][col] += 1;
          i++;
        }
      }

      maxArea = max(maxArea, reactangleHistogram(histograms[row]));
    }
    return maxArea;
  }

 private:
  int reactangleHistogram(const vector<int>& histogram) {
    stack<int> stk;
    int i = 0, maxArea = 0;

    while (i <= histogram.size()) {
      int curHeight = (i == hisgotram.size()) ? -1 : histogram[i];

      if (stk.empty() || curHeight > histogram[stk.top()]) {
        stk.push(i++);
        continue;
      }

      int height = histogram[stk.top()];
      stk.pop();
      int leftIndex = stk.empty() ? -1 : stk.top();
      int rightIndex = i;
      maxArea = max(maxArea, height * (rightIndex - leftIndex - 1));
    }
    return maxArea;
  }
};