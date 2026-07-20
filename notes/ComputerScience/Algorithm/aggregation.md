Mergesort 方向

  1. 21. Merge Two Sorted Lists (https://leetcode.com/problems/merge-two-sorted-lists/) - Easy
     练合并两个有序序列，是归并排序的最小基本功。
  2. 88. Merge Sorted Array (https://leetcode.com/problems/merge-sorted-array/) - Easy
     练数组原地合并，重点是双指针从后往前。
  3. 912. Sort an Array (https://leetcode.com/problems/sort-an-array/) - Medium
     正式手写归并排序，要求 O(n log n)，不要用内置排序。
  4. 148. Sort List (https://leetcode.com/problems/sort-list/) - Medium
     链表归并排序经典题，重点是快慢指针切分 + 合并链表。
  5. 23. Merge k Sorted Lists (https://leetcode.com/problems/merge-k-sorted-lists/) - Hard
     可以用分治归并做，不只用堆。适合练“多路归并”。
  6. 315. Count of Smaller Numbers After Self (https://leetcode.com/problems/count-of-smaller-numbers-after-self/) - Hard
     归并排序进阶：在 merge 过程中统计右侧更小数量。
  7. 493. Reverse Pairs (https://leetcode.com/problems/reverse-pairs/) - Hard
     归并计数经典难题，核心是先统计跨区间贡献，再归并。
  8. 327. Count of Range Sum (https://leetcode.com/problems/count-of-range-sum/) - Hard
     前缀和 + 归并计数，难度比 315/493 更抽象。

  Hashsort / 哈希 + 排序方向

  1. 242. Valid Anagram (https://leetcode.com/problems/valid-anagram/) - Easy
     哈希计数或排序都能做，适合入门对比两种思路。
  2. 349. Intersection of Two Arrays (https://leetcode.com/problems/intersection-of-two-arrays/) - Easy
     哈希去重 + 排序可选，练 set/map 基础。
  3. 350. Intersection of Two Arrays II (https://leetcode.com/problems/intersection-of-two-arrays-ii/) - Easy
     哈希计数版交集，理解频次。
  4. 49. Group Anagrams (https://leetcode.com/problems/group-anagrams/) - Medium
     哈希 key 可以是排序后的字符串，也可以是 26 维计数。
  5. 347. Top K Frequent Elements (https://leetcode.com/problems/top-k-frequent-elements/) - Medium
     哈希统计 + 桶排序 / 堆 / quickselect，建议先写桶排序。
  6. 451. Sort Characters By Frequency (https://leetcode.com/problems/sort-characters-by-frequency/) - Medium
     频率排序，哈希表 + bucket sort 很自然。
  7. 692. Top K Frequent Words (https://leetcode.com/problems/top-k-frequent-words/) - Medium
     哈希统计 + 排序规则，重点是同频按字典序。
  8. 791. Custom Sort String (https://leetcode.com/problems/custom-sort-string/) - Medium
     哈希计数 + 自定义顺序排序。
  9. 1122. Relative Sort Array (https://leetcode.com/problems/relative-sort-array/) - Easy
     哈希计数 / 计数排序，适合练“按给定顺序排序”。
  10. 220. Contains Duplicate III (https://leetcode.com/problems/contains-duplicate-iii/) - Hard
     进阶哈希桶题，虽然不是排序题，但很适合 hashtable + bucket 思维。


对于数组的归并排序来说，实现上很难避免额外的临时数组拷贝。
```cpp
class Solution {
public:
    vector<int> sortArray(vector<int>& nums) {
        if (nums.size() <= 1) {
            return nums;
        }
        
        mergeSort(nums, 0, nums.size());
        return nums;
    }

private:
    void mergeSort(vector<int>& nums, int i, int j) {
        int cnt = j - i;
        // two elements, just merge.
        if (cnt == 2) {
            merge(nums, i, i + 1, j);
            return;
        } else if (cnt == 1 || cnt == 0) {
            return;
        }

        int mid = (i + j) / 2;
        mergeSort(nums, i, mid);
        mergeSort(nums, mid, j);
        merge(nums, i, mid, j);
        // nums[i] to nums[j] is sorted.
        return;
    }

    // merge two non-descring array
    // nums1: nums[l] ... nums[m-1]
    // nums2: nums[m] ... nums[n-1]
    void merge(vector<int>& nums, int l, int m, int n) {
        int i = l, j = m;
        // temperary space seems can not be avoid.
        std::vector<int> res(n - l);
        int k = 0;

        while (i < m && j < n) {
            if (nums[i] <= nums[j]) {
                res[k++] = nums[i++];
            } else {
                res[k++] = nums[j++];
            }
        }

        while (i < m) {
            res[k++] = nums[i++];
        }

        while (j < n) {
            res[k++] = nums[j++];
        }

        std::copy(res.begin(), res.end(), nums.begin() + l);
    }
};
```
merge的时候不论是返回新的数组还是把新的数组写回原来的数组，都无法避免额外分配 O(n) 的内存。