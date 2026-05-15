class Solution {
 public:
  bool searchMatrix(vector<vector<int>>& matrix, int target) {
    const int nrow = matrix.size();
    cout << nrow << endl;
    if (nrow == 0) return false;

    const int ncol = matrix[0].size();
    if (ncol == 0) return false;

    int erow = nrow - 1, ecol = ncol - 1;

    int srow = 0;
    while (srow + 1 < erow) {
      int mid = srow + (erow - srow) / 2;
      if (matrix[mid].front() == target)
        return true;
      else if (matrix[mid].front() < target)
        srow = mid;
      else
        erow = mid;
    }
    if (matrix[erow].front() == target)
      return true;
    else if (matrix[erow].front() < target)
      srow = erow;

    int scol = 0;
    while (scol + 1 < ecol) {
      int mid = scol + (ecol - scol) / 2;
      if (matrix[srow][mid] == target)
        return true;
      else if (matrix[srow][mid] < target)
        scol = mid;
      else
        ecol = mid;
    }

    if (matrix[srow][scol] == target) return true;
    if (matrix[srow][ecol] == target) return true;
    return false;
  }
};