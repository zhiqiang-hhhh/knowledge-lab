class Solution {
 public:
  double findMedianSortedArrays(vector<int>& nums1, vector<int>& nums2) {
    const int total = nums1.size() + nums2.size();
    if (total % 2 == 0) {
      return (findKth(nums1, nums1.begin(), nums2, nums2.begin(), total / 2) +
              findKth(nums1, nums1.begin(), nums2, nums2.begin(),
                      total / 2 + 1)) /
             2.0;
    }
    return findKth(nums1, nums1.begin(), nums2, nums2.begin(), total / 2 + 1);
  }
  int findKth(const vector<int>& numsA, vector<int>::iterator startA,
              const vector<int>& numsB, vector<int>::iterator startB, int k) {
    if (startA >= numsA.end()) {
      return *(startB + k - 1);
    }

    if (startB >= numsB.end()) {
      return *(startA + k - 1);
    }
    if (k == 1) {
      return min(*startA, *startB);
    }

    int halfKthofA =
        (startA + k / 2 - 1) >= numsA.end() ? INT_MAX : *(startA + k / 2 - 1);

    int halfKthofB =
        (startB + k / 2 - 1) >= numsB.end() ? INT_MAX : *(startB + k / 2 - 1);

    if (halfKthofA < halfKthofB) {
      return findKth(numsA, startA + k / 2, numsB, startB, k - k / 2);
    } else {
      return findKth(numsA, startA, numsB, startB + k / 2, k - k / 2);
    }
  }
};