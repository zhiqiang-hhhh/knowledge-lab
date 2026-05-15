class Solution {
 public:
  int findPeakElement(vector<int>& nums) {
    if (nums.size() == 0) return -1;

    int start = 0, end = nums.size() - 1;
    while (start + 1 < end) {
      int mid = start + (end - start) / 2;
      if (nums[mid] > nums[mid - 1] && nums[mid] > nums[mid + 1])
        return mid;
      else if (nums[mid] < nums[mid + 1])
        start = mid;
      else if (nums[mid] < nums[mid - 1])
        end = mid;
    }

    return (nums[start] > nums[end]) ? start : end;
  }
};