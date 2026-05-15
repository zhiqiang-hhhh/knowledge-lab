# 二分查找
## 287.Find the Duplicate Number
输入大小为 n + 1 的整数数组，数组中的元素值范围为 1 到 n。**不能修改输入数组**，要求找到其中重复的元素。

**整个数组中有且仅有一个重复元素，重复元素可以出现不止两次**

如果可以修改输入的数组，那么最简单的方法是对输入进行排序，在有序数组中找到重复元素就很简单了。这种方式需要$O(nlog n)$的运行时间。或者利用HashSet，这种方式需要额外O(n)的存储空间。

仔细想，如果对整个数组排序，其中对重复元素之后的元素排序是无用功。所以有优化的空间。

排序后的数组中，如果没有重复，那么元素 m 一定出现在第 m 个位置上。所以我们可以遍历输入，如果元素 m 在第 m 个位置上，那么跳过；否则，我们先检查 m 和第 m 个位置上的元素是否相等，如果相等，说明 m 就是重复元素，如果不相等，那么我们交换这两个元素，保证 m 在它应该出现的位置。同时，对被交换过来的元素，继续上述过程，直到遇到重复，或者当前位置元素处在正确的位置。

代码如下：
```c++
int duplicate(vector<int>& nums){
    int i = 0;
    while(i <= nums.size()){
        if(nums[i] == i + 1){
            i++;
            continue;
        }

        // nums[i] 位置不对
        if(nums[i] == nums[nums[i] - 1])
            return nums[i];
        else{
            swap(nums[i], nums[nums[i] - 1]);
        }
    }
}
```
现在考虑本题中不能修改输入数组的情况。

关键是用好输入数组中元素范围不超过数组大小的条件。假设输入数组中一共 n 个元素，则元素值范围为 1 ~ n。将元素值分为两部分，第一部分 [1 ~ mid]，第二部分 [mid + 1, n]。如果[1 ~ mid]这些元素在数组中出现的次数超过 mid - 1 + 1次，那么说明重复元素一定在[1 ~ mid]之间；否则，由于一定有重复元素，那么重复元素一定在 [mid + 1, n]之间。当确定区间之后，我们只需要在半个区间中继续查找过程。直到区间中只剩下一个元素。
```c++
class Solution {
 public:
  int findDuplicate(vector<int>& nums) {
    int left = 1, right = nums.size();

    while (left < right) {
      auto mid = left + ((right - left) >> 1);
      int count = calCount(nums, left, mid);
      // cout << mid << ' ' << count << endl;
      if (count > mid - left + 1) {
        right = mid;
      } else {
        left = mid + 1;
      }
    }
    return left;
  }
  int calCount(const vector<int>& nums, int left, int right) {
    int cnt = 0;
    for (auto& num : nums) {
      if (left <= num && num <= right) ++cnt;
    }
    return cnt;
  }
};
```
二分的次数为$O(log n)$，每次calCount的运行时间为$O(n)$，所以整体时间为$O(n logn)$，额外运行空间为$O(1)$。
