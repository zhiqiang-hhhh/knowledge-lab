class Solution {
 public:
  void merge(vector<int>& nums1, int m, vector<int>& nums2, int n) {
    size_t tail = m + n - 1;
    m -= 1;
    n -= 1;
    while (n >= 0) {
      nums1[tail--] =
          (m >= 0) && (nums1[m] >= nums2[n]) ? nums1[m--] : nums2[n--];
    }
  }
};
