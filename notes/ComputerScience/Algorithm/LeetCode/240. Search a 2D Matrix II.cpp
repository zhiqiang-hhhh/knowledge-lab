class Solution {
 public:
  bool searchMatrix(vector<vector<int>>& matrix, int target) {
    if (matrix.size() == 0 || matrix.front().size() == 0) return false;
    const int erow = matrix.size() - 1;
    const int ecol = matrix.front().size() - 1;
    int prow = erow, pcol = 0;
    while (prow >= 0 && pcol <= ecol) {
      if (matrix[prow][pcol] == target)
        return true;
      else if (matrix[prow][pcol] < target)
        pcol += 1;
      else
        prow -= 1;
    }
    return false;
  }
};