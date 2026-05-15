// Forward declaration of isBadVersion API.
bool isBadVersion(int version);

class Solution {
 public:
  int firstBadVersion(int n) {
    if (n == 0) return n;
    int start = 1, end = n;
    while (start + 1 < end) {
      int mid = start + (end - start) / 2;
      if (isBadVersion(mid))
        end = mid;
      else
        start = mid;
    }
    if (isBadVersion(start)) return start;
    return end;
  }
};