class Solution {
 public:
  vector<vector<int>> intervalIntersection(vector<vector<int>>& A,
                                           vector<vector<int>>& B) {
    vector<vector<int>> ret;

    for (int i = 0, j = 0; i < A.size() && j < B.size();) {
      if (A[i].back() < B[j].front()) {
        i++;
      } else if (B[j].back() < A[i].front()) {
        j++;
      }

      else {
        ret.push_back(
            {max(A[i].front(), B[j].front()), min(A[i].back(), B[j].back())});

        A[i].back() > B[j].back() ? j++ : i++;
      }
    }
    return ret;
  }
};