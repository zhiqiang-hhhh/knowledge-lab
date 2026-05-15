class Solution {
 public:
  bool search(vector<int>& nums, int target) {
    if (nums.size() <= 0) return false;

    int start = 0, end = (int)nums.size() - 1;
    while (start + 1 < end) {
      while (nums[start] == nums[start + 1] && start + 1 < end) {
        start++;
      }
      while (nums[end] == nums[end - 1] && start + 1 < end) {
        end--;
      }

      int mid = start + (end - start) / 2;
      if (nums[mid] == target) return true;

      if (nums[mid] > nums[start]) {
        if (nums[start] <= target && target < nums[mid]) {
          end = mid;
        } else {
          start = mid;
        }
      } else if (nums[mid] < nums[end]) {
        if (nums[end] >= target && target > nums[mid]) {
          start = mid;
        } else {
          end = mid;
        }
      }
      /*
      // mid <= start, mid >= end
      else if(nums[start] > nums[mid]){
          // nums[mid] == nums[end]
          end--;
      } else if(nums[mid] > nums[end]) {
          // nums[start] == nums[mid]
          start++;
      } else{
          // start = mid = end
          start++;
          end--;
      } */
    }
    if (nums[start] == target || nums[end] == target) return true;
    return false;
  }
};