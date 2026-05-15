class Solution {
 public:
  int findMin(vector<int>& nums) {
    if (nums.size() == 1) {
      return nums.front();
    }
    int start = 0, end = nums.size() - 1;
    int mid;
    while (start + 1 < end) {
      if (nums[start] < nums[end]) {
        return nums[start];
      }
      mid = start + (end - start) / 2;

      if (nums[mid] > nums[start]) {
        start = mid;
      } else {
        end = mid;
      }
    }
    return nums[start] > nums[end] ? nums[end] : nums[start];
  }
};