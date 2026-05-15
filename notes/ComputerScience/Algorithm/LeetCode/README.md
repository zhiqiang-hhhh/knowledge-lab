
- [LeetCode](#leetcode)
    - [2020/5/23](#2020523)
      - [268. Missing Number](#268-missing-number)
      - [136. Single Number](#136-single-number)
    - [2020/3/5](#202035)
      - [81. Search in Rotated Sorted Array II[第二遍]](#81-search-in-rotated-sorted-array-ii%e7%ac%ac%e4%ba%8c%e9%81%8d)
    - [2020/3/2](#202032)
      - [3. Longest Substring Without Repeating Characters](#3-longest-substring-without-repeating-characters)
      - [169. Majority Element](#169-majority-element)
      - [229. Majority Element II](#229-majority-element-ii)
    - [2020/3/1](#202031)
      - [1. Two Sum](#1-two-sum)
      - [15. 3Sum](#15-3sum)
      - [18 4Sum](#18-4sum)
      - [167. Two Sum II - Input array is sorted](#167-two-sum-ii---input-array-is-sorted)
      - [653. Two Sum IV - Input is a BST](#653-two-sum-iv---input-is-a-bst)
    - [2020/2/29](#2020229)
      - [239. Sliding Window Maximum](#239-sliding-window-maximum)
    - [2020/2/28](#2020228)
      - [24. Swap Nodes in Pairs](#24-swap-nodes-in-pairs)
      - [25. Reverse Nodes in k-Group[Hard]](#25-reverse-nodes-in-k-grouphard)
    - [2020/2/27](#2020227)
      - [8. String to Integer (atoi)](#8-string-to-integer-atoi)
      - [22. Generate Parentheses](#22-generate-parentheses)
      - [92. Reverse Linked List II](#92-reverse-linked-list-ii)
      - [83. Remove Duplicates from Sorted List](#83-remove-duplicates-from-sorted-list)
      - [94. Binary Tree Inorder Traversal](#94-binary-tree-inorder-traversal)
      - [144. Binary Tree Preorder Traversal](#144-binary-tree-preorder-traversal)
    - [2020/2/26](#2020226)
      - [124. Binary Tree Maximum Path Sum[Hard]](#124-binary-tree-maximum-path-sumhard)
      - [LintCode Binary Tree Maximum Path Sum II](#lintcode-binary-tree-maximum-path-sum-ii)
      - [236. Lowest Common Ancestor of a Binary Tree](#236-lowest-common-ancestor-of-a-binary-tree)
    - [2020/2/14](#2020214)
      - [215. Kth Largest Element in an Array](#215-kth-largest-element-in-an-array)
    - [2020/2/12](#2020212)
      - [154. Find Minimum in Rotated Sorted Array II [Hard]](#154-find-minimum-in-rotated-sorted-array-ii-hard)
    - [2020/2/7](#202027)
      - [50. Pow(x, n)](#50-powx-n)
      - [69. Sqrt(x)](#69-sqrtx)
      - [300. Longest Increasing Subsequence](#300-longest-increasing-subsequence)
    - [2020/2/6](#202026)
      - [4. Median of Two Sorted Arrays [Hard][2020/2/15]](#4-median-of-two-sorted-arrays-hard)
    - [2020/2/4](#202024)
      - [153. Find Minimum in Rotated Sorted Array](#153-find-minimum-in-rotated-sorted-array)
      - [33. Search in Rotated Sorted Array](#33-search-in-rotated-sorted-array)
      - [81. Search in Rotated Sorted Array II](#81-search-in-rotated-sorted-array-ii)
    - [2020/2/2](#202022)
      - [162. Find Peak Element](#162-find-peak-element)
      - [278. First Bad Version](#278-first-bad-version)
      - [74. Search a 2D Matrix](#74-search-a-2d-matrix)
      - [240. Search a 2D Matrix II](#240-search-a-2d-matrix-ii)
    - [2020/2/1](#202021)
      - [34. Find First and Last Position of Element in Sorted Array](#34-find-first-and-last-position-of-element-in-sorted-array)
      - [35. Search Insert Position](#35-search-insert-position)
    - [2020/1/17](#2020117)
      - [57. Insert Intervals](#57-insert-intervals)
    - [2020/1/10](#2020110)
      - [56. Merge Intervals[2020/2/16]](#56-merge-intervals2020216)
    - [2020/1/8](#202018)
      - [红黑树](#%e7%ba%a2%e9%bb%91%e6%a0%91)
    - [2020/1/7](#202017)
      - [LintCode 448. Inorder Successor in BST](#lintcode-448-inorder-successor-in-bst)
      - [235. Lowest Common Ancestor of a Binary Search Tree](#235-lowest-common-ancestor-of-a-binary-search-tree)
      - [701. Insert into a Binary Search Tree](#701-insert-into-a-binary-search-tree)
      - [145. Binary Tree Postorder Traversal](#145-binary-tree-postorder-traversal)
    - [2020/1/6](#202016)
      - [94. Binary Tree Inorder Traversal](#94-binary-tree-inorder-traversal-1)
      - [230. Kth Smallest Element in a BST](#230-kth-smallest-element-in-a-bst)
    - [2020/1/4](#202014)
    - [2020/1/3](#202013)
      - [88.Merge Sorted Array](#88merge-sorted-array)
      - [75.Sort Colors](#75sort-colors)
      - [148. Sort List](#148-sort-list)
      - [912. Sort An Array](#912-sort-an-array)

# LeetCode

LeetCode Record

归并快排的区别：
1. 思想不同：归并从局部到整体，快排从整体到局部
2. 稳定性：归并是稳定排序，快排不是稳定排序
3. 运行时间：归并 $\Theta(n)logn$，快排只是平均情况下为 nlogn，但是快排的系数要小一点
4. 空间复杂度：对于数组来说，快排可以O(1)，而归并需要O(n)；对于链表来说则都是O(1)

### 2020/5/23
#### 268. Missing Number
位图法。给定从 0 ~ n 之间选取的 n 个不同的数。要求找到其中的 missing number。

解释直接抄LeetCode评论区了

For people who don't understand this solution: what he's doing is he's using the bitwise XOR operator to single out the missing number. How? First, we need to understand the properties of XOR: firstly, XOR'ing a number by itself results in 0. So if we have 1 ^ 1, this will equal 0. Secondly, XOR is commutative and associative - what this means is we can re-order our XOR operations in any way we want and it will result in the same value we would have if we didn't. Finally, a number XOR'd by 0 will result in the same number unchanged. So, essentially, by XOR'ing all the numbers from 0 to n, and all the numbers in the array, we will end up XOR'ing 2 of every number except for the missing one. As we know, it doesn't matter which order we XOR these numbers in - as long as we XOR 2 of the same number, it will result in 0. So eventually we will get 0 ^ the missing number, which, due to the third property I mentioned, will simply equal the missing number. If you're not convinced as to how these properties work, I would recommend taking a quick look as to how they work.
    
```c++
class Solution {
 public:
  int missingNumber(vector<int>& nums) {
    int ret = nums.size();
    int i = 0;

    for (auto& num : nums) {
      ret ^= num;  // 按位异或
      ret ^= i;
      i++;
    }

    return ret;
  }
};
```
#### 136. Single Number

给定n个元素的数组，其中的 n-1 个元素都出现了两次，只有一个元素出现了一次，要求找出该元素。

做法：类似的按位异或方法。

0 ^ N = N
N ^ N = 0

So..... if N is the single number

N1 ^ N1 ^ N2 ^ N2 ^..............^ Nx ^ Nx ^ N

= (N1^N1) ^ (N2^N2) ^..............^ (Nx^Nx) ^ N

= 0 ^ 0 ^ ..........^ 0 ^ N

= N

### 2020/3/5
#### 81. Search in Rotated Sorted Array II[第二遍]
今天面试遇到这道题了。当场很勉强做出来，但是事后想想好多细节还是没有想清楚。
希望本次记录彻底解决本题。

首先，这道题如果没有重复元素，那么很简单：
```c++
while(start + 1 < end){
    mid = start + (end - start) / 2;
    if(nums[mid] == target)
        return true;
    if(nums[mid] > nums[start]){ // mid 处于前一线段
        if(nums[start] <= target && target < nums[mid])// 注意一定是 nums[start] <= target
            end = mid;
        else
            start = mid;
    }
    else{
        // nums[mid] < nums[end]
        if(nums[mid] < target && target <= nums[end])// 注意这一一定是 target <= nums[end]
            start = mid;
        else
            end = mid;
    }
}
```
唯一需要注意的就是 nums[start] 和 nums[end] 有可能直接等于 target，一定要考虑这种情况，否则会移错区间。比如当 nums[start] == target，但是代码为 
```c++
if(nums[start] < target && target < nums[mid])
    end = mid;
else
    start = mid;
```
会错误地将执行 start = mid

现在处理出现重复元素的情况。最直观的想法是将本情况手动转换成之前不重复的情况。事实上这也是个人觉得最好的最简洁的做法。

如何转换呢，由于输入数组是从有序序列旋转得到的，那么旋转之后重复元素只可能出现在：
1. 全部为重复元素
2. 出现在头或者尾或者同时出现在尾和头。

那么说明我们只需要判断头尾即可，所以我们可以在循环前部处理，将前后重复的部分消除。
```c++
while(nums[start] == nums[start + 1] && start + 1 < end)
    start++;
while(nums[end] == nums[end - 1] && start + 1 < end)
    end--;
```
这样处理之后，唯一可能还剩下的重复情况就是 nums[start] == nums[end]，数组中其他所有元素都是不相等的。这时这两个相等的元素其实对我们最后的判断已经没有影响了，因为在前面我们已经考虑过 
nums[start] == target 以及 nums[end] == target 的情况了，而我们的目的只是判断 nums 中是否有 target，所以不论最后找到的位置是 start 还是 end 都可以。
完整代码：
```c++
class Solution {
public:
    bool search(vector<int>& nums, int target) {
        if(nums.size() <= 0)
            return false;
        
        int start = 0, end = (int)nums.size() - 1;
        while(start + 1 < end){
            // 处理头尾重复元素
            while(nums[start] == nums[start + 1] && start + 1 < end){
                start++;
            }
            while(nums[end] == nums[end - 1] && start + 1 < end){
                end--;
            }
            
            // 按照无重复元素处理
            int mid = start + (end - start) / 2;
            if(nums[mid] == target)
                return true;
            
            if(nums[mid] > nums[start]){
                if(nums[start] <= target && target < nums[mid]){
                    end = mid;
                }
                else{
                    start = mid;
                }
            }
            else if(nums[mid] < nums[end]){
                if(nums[end] >= target && target > nums[mid]){
                    start = mid;
                }
                else{
                    end = mid;
                }
            }
        }
        if(nums[start] == target || nums[end] == target)
                return true;
        return false;
    }       
};
```
如果我们不用这种方法，那么我们需要更加深入地去判断每种可能出现地情况。

当 nums[mid] > nums[start] 和 nums[mid] < nums[end] 都不满足时，则： numd[start] <= nums[mid] 并且 nums[mid] >= nums[end]

如果我们再仔细想，由于数组旋转之前整体有序，那么旋转之后得到的两条线段本身应该是有序的，而且，nums[start] 一定会**大于等于** nums[end]，那么
1. 当 nums[start] < nums[mid] 时，nums[mid] 只可能等于 nums[end]，而不可能大于 nums[end]；
2. 当 nums[mid] > nums[end] 时，nums[start] 只可能等于 nums[mid]，而不可能小于nums[mid]

这样其实我们就很好做了：
```c++
    // nums[mid] <= nums[start] && nums[mid] >= nums[end]
    else if(nums[start] > nums[mid]){ // nums[mid] == nums[end]
        end--;
    } else if(nums[mid] > nums[end]) { // nums[start] == nums[mid]
        start++;
    } else{ // start = mid = end
        start++;
        end--;
    }         
```
完整代码如下：
```c++
class Solution {
 public:
  bool search(vector<int>& nums, int target) {
    if (nums.size() <= 0) return false;

    int start = 0, end = (int)nums.size() - 1;
    while (start + 1 < end) {
   
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
      }
    }
    if (nums[start] == target || nums[end] == target) return true;
    return false;
  }
};
```

### 2020/3/2
#### 3. Longest Substring Without Repeating Characters

DP，memo[i] 用来记录当前 i 位置时的最大长度，额外需要一个 HashMap 记录每个字符出现的最近的位置。

#### 169. Majority Element
找出数组中出现次数大于 n/2 的元素，n 为数组的大小。题目中明确说明该元素一定存在。

做法很多，包括有 HashMap，nth_element 等。
但是我个人觉得最好的方法是使用摩尔投票算法。摩尔投票算法只需要 O(1) 额外空间，运行时间为 O(n).
#### 229. Majority Element II
选出出现次数大于 n/3 的元素。本题中并不一定会出现该元素，所以需要 round 2 来判断是否将元素加入 result。

关于摩尔投票算法，在 LeetCode 讨论区中找到一个人的回答很好，直接贴过来

First, we claim: **given n numbers and the k counters, only less than n/(k+1) times pair-out can happen.**
That is to say:

1. given n numbers and 1 counter (which is the majority element problem), at most (n/2) times pair-out can happen, which will lead to the survival of the only element that appeared more than n/2 times.
2. given n numbers and 2 counters (which is our case), at most n/3 times of pair-out can happen, which will lead to the survival of elements that appeared more than n/3 times.
3. given n numbers and k counters, at most (n/k+1) times of pair-out can happen, which will lead to the survival of elements that appeared more than n/(k+1) times.
If this is the case, then n elements using two counters can at most pair out less than (n/3) times, which will result in the survival of the elements that appears more than (n/3) times.

First we look at an example of one counter:
suppose nums = [1, 2, 3, 4, 5, 6], and we are finding only one candidate and we have only one counter.

the procedure will be like this:

    candidate = 1, counter = 1

    current number = 2
    candidate = 1, counter = 0
    (one pair-out happens)

    current number = 3
    candidate = 3, counter = 1
    (pair-out cannot happen now since there's nothing to pair out! Instead, counter got increased!)

    current number = 4
    candidate = 3, counter = 0
    (one pair-out happens)

    current number = 5
    candidate = 5, counter = 1
    (pair-out cannot happen and counter increased!)

    curent number = 6
    candidate = 5, counter = 0
    (one pair-out happens)

From the above example, there are 6 elements in nums and we paired out 3 times, which is the most we can get. Suppose nums = [1,1,1,1,2,3], now we see that pair-out can happen only twice in this case.

From the above example,**it's obvious that to pair out once, you have to increase the counter at least once.**
And to pair out some candidate, you need first increase the counter. **And every time you increase the counter, you waste one chance to pair out**. So given n numbers, you can at most pair out (n/2) times, since you have to at least increase the counter (n/2) times to let you have something to pair out. It's quite like the amortized analysis, but if you don't know that, it doesn't matter though.

Now we still use the example above but we hope to find two candidates:
suppose nums = [1, 2, 3, 4, 5, 6], and we are finding two candidates and we have two counters.

the procedure will be like this:

    candidate1 = 1, counter1 = 1    
    candidate2 = 2, counter2 = 1

    current number = 3
    candidate1 = 1, counter1 = 0
    candidate2 = 2, counter2 = 0
    (one pair-out happens and both counters got decreased.)

    current number = 4
    candidate1 = 4, counter = 1
    candidate2 = 2, counter2 = 0
    (pair-out cannot happen and counter1 got increased)

    current number = 5
    candidate1 = 4, counter1 = 1
    candidate2 = 5, counter2 = 1
    (pair-out can still not happen and counter2 got incresed)

    current number = 6
    candidate1 = 4, counter1 = 0
    candidate2 = 5, counter2 = 0
    (pair-out happens and both counters become 0)

Now we see, there are 6 elements in nums and we paired out 2 times, which is also the most we can get. Suppose nums = [1,1,1,1,2,3], pair-out can happen only once in this case.

This is because once pair-out happens, both counters decrease. And when some counter becomes 0, only one counter will get increased at a time. So to pair out m times, each counter have to be increased at least m times, which is to increase 2*m times totally.

It's not difficult to generalize to k counters. Of course, when k is large, it may be not efficient to use this count-and-pair-out method. However, the algorithm is still worth learning.

Hope it helps :)

### 2020/3/1
#### 1. Two Sum
    Given nums = [2, 7, 11, 15], target = 9,

    Because nums[0] + nums[1] = 2 + 7 = 9,
    return [0, 1].

这道题比较简单，并且题目中明确：只有一个 solution，即一组数中只有一对数满足要求。而且，本题要求返回的是元素的位置，所以排序的方法单对本题来说并不适用。

1. 暴力解法就是 O(n*n)，两个 loop 遍历。
2. 利用 HashMap
   HashMap 维护 val->pos 的映射，对于每一个 val 如果 target - val 在 HashMap 中，那么就认为找到了目标。HashMap 的查找和插入在平均情况下时间为 O(1)，整个算法运行时间则为 O(n)

需要注意的是在方法二中，HashMap 不能包含带查找元素自身，否则就会出现 Duplicate
```c++
class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        vector<int> res;
        unordered_map<int, int> hm;
        
        for(int i = 0; i < nums.size(); i++){
            auto t = hm.find(target - nums[i]);
            if(t != hm.end()){
                res.push_back(i);
                res.push_back(t->second);
                break;
            }
            // 防止重复
            hm[nums[i]] = i;
        }
        return res;
};
```
#### 15. 3Sum
    Given array nums = [-1, 0, 1, 2, -1, -4],

    A solution set is:
    [
        [-1, 0, 1],
        [-1, -1, 2]
    ]
这道题似乎和 Two Sum 一样，但其实本题与 1 Two Sum 完全不同。
3Sum 要求**所有**满足条件且不重复的元素的组合，而不是 position 的组合。

本题的步骤
1. 排序：关键步骤，排序之后可以帮助消除重复，帮助查找目标
2. 由于数组排序，那么选 i = begin, j = end;
    如果 num[i] + num[j] < target，则 i++；
    如果 num[i] + num[j] > target，则 j--
    否则找到一组满足条件的值，找到之后需要消除重复

```c++
  for(int a = 0; a <= (int)nums.size() - 3; a++){
            // 消除 a 重复
            if((a >= 1) && nums[a] == nums[a - 1])
                continue;
            
            int b = a + 1, c = nums.size() - 1;
            
            while(b < c){
                if(nums[a] + nums[b] + nums[c] < 0){
                    b++;
                }
                else if(nums[a] + nums[b] + nums[c] > 0){
                    c--;
                }
                else{
                    vector<int> temp{nums[a], nums[b++], nums[c--]};
                    res.push_back(temp);
                    // 消除 b 重复
                    while(b < c && nums[b] == nums[b - 1])
                        b++;
                    // 消除 c 重复
                    while(b < c && nums[c] == nums[c + 1])
                        c--;
                }
            }
        }
```

#### 18 4Sum
与 15 3Sum 方法思路相同。

#### 167. Two Sum II - Input array is sorted
这道题应该是15题和18题的基础版本，最简单情况下的版本。
#### 653. Two Sum IV - Input is a BST
输入为二叉搜索树，因此需要一个 iterator 用来获取BST中序遍历的值。

本题相当于 167.Two Sum II - Input array is sorted 和  173. Binary Search Tree Iterator 的结合题

### 2020/2/29
#### 239. Sliding Window Maximum

    Input: nums = [1,3,-1,-3,5,3,6,7], and k = 3
    Output: [3,3,5,5,6,7] 
    Explanation: 

    Window position                Max
    ---------------               -----
    [1  3  -1] -3  5  3  6  7       3
    1 [3  -1  -3] 5  3  6  7       3
    1  3 [-1  -3  5] 3  6  7       5
    1  3  -1 [-3  5  3] 6  7       5
    1  3  -1  -3 [5  3  6] 7       6
    1  3  -1  -3  5 [3  6  7]      7

滑动窗口，第一时间想到是使用优先队列。就是将每个窗口中的 k 个元素都放入一个最大堆，这种方法运行时间为元素数量 N * O(K)。
为什么是 O(K) 呢，因为如果每次构建大顶堆时都是使用 insert 方法的话，那么运行时间是 K*logK。但是如果预先给好 K 个元素，那么把这 K 个元素放入 K 大小的数组，直接由数组构建的话运行时间是 O(K)。

最佳方法是使用双端队列 Deque
该方法的原理基于一个这样的事实，就是如果 window 中某个元素 x 之后有比它大的元素 y，那么 x 永无出头之日。因为 x 比 y 先进入 window，当 y 存在时 x 永远不是 max，而且 x 比 y 先走。
实际实现时，我们在 window 中保存索引而不是值本身，因为这样我们可以保存更多信息。
```c++
class Solution {
public:
    vector<int> maxSlidingWindow(vector<int>& nums, int k) {
        if(nums.empty())
            return vector<int>();
        deque<int> window;
        vector<int> res;
        for(int i = 0; i < nums.size(); i++){
            if(!window.empty() && window.front() == i - k)
                window.pop_front();
            // 把 window 中所有小于新加入元素的值都干掉
            while(!window.empty() && nums[window.back()] < nums[i]){
                window.pop_back();
            }
            window.push_back(i);
            if(i >= k - 1)
                res.push_back(nums[window.front()]);
        }
        return res;
    }
};
```

### 2020/2/28
#### 24. Swap Nodes in Pairs
链表反转，以两个元素为一组进行反转。
核心是保持 prev 与 cure 的相对位置以及连接关系在循环开始之前 与 结束之后的状态一致。

本题 prev 始终指向 cure 前的第一个位置，而 cure 指向准备 swap 的第一个位置。而且在循环开始之前和之后，永远保持 prev->cure
```c++
class Solution {
 public:
  ListNode* swapPairs(ListNode* head) {
    ListNode* dummy = new ListNode(0);
    dummy->next = head;
    ListNode* res = (head == NULL || head->next == NULL) ? head : head->next;

    // 循环开始之前 prev->cure
    ListNode* prev = dummy;
    ListNode* cure = head;

    while (cure != NULL) {
      cure = cure->next;

      if (cure != NULL) {
        ListNode* temp = cure->next;
        cure->next = prev->next;
        prev->next = cure;
        prev = cure->next;
        cure = temp;
        // 保持 prev->cure 状态
        prev->next = cure;
      }
    }

    delete dummy;
    return res;
  }
};
```
#### 25. Reverse Nodes in k-Group[Hard]
链表反转题目，以 k 个元素为一组进行反转
转换为两次 Reverse，第一次是将 k 个元素反转，第二次是将反转之后的子链重新加入原先链表，因此需要两个 prev，pprev 用来记录原来的位置，prev 与 cure 负责进行两两反转。

画图帮助理解，保持每次 while 循环以及 for 循环之后，pprev、prev以及cure的相对位置不变。
```c++
class Solution {
public:
    ListNode* reverseKGroup(ListNode* head, int k) {
        ListNode* dummy = new ListNode(0);
        dummy->next = head;
        
        // while 循环之前 pprev=prev->cure
        // cure 指向未来 k 个元素的第一个元素
        ListNode* pprev = dummy;
        ListNode* prev = dummy;
        ListNode* cure = head;
        
        while(cure != NULL){
            ListNode* guard = prev;
            // guard 用来探路
            for(int i = 0; i < k && guard != NULL; i++){
                guard = guard->next;
            }
            if(guard == NULL)
                break;
            
            for(int i = 0; i < k && cure != NULL; i++){   
               ListNode* temp = cure->next;
               cure->next = prev;
               prev = cure;
               cure = temp;
           }
            ListNode* temp = pprev->next;
            pprev->next = prev;
            pprev = temp;
            // 维持 prev pprev 和 cure 的相对位置不变
            prev = pprev;
            prev->next = cure;
        }
        
        head = dummy->next;
        delete dummy;
        return head;
    }
};
```
### 2020/2/27
#### 8. String to Integer (atoi)
时刻注意有没有越界。
```c++
class Solution {
public:
    int myAtoi(string str) {
        if(str.size() == 0)
            return 0;
        int indicator = 1;
        __int64_t result = 0;
        
        int i = str.find_first_not_of(' ');
        if(i >= str.size())
            return 0;
        if(str[i] == '+' || str[i] == '-'){
            indicator = (str[i++] == '-') ? -1 : 1;
        }
        
        while(i < str.size() && str[i] >= '0' && str[i] <= '9'){
            result = result * 10 + str[i++] - '0';
            if(result * indicator >= INT32_MAX) return INT32_MAX;
            if(result * indicator <= INT32_MIN) return INT32_MIN;
        }
        return result * indicator;
    }
};
```

#### 22. Generate Parentheses
给定整数 n，找出 n 对括号一共可以有多少正确组合。

要点：
1. 首先添加的必须是左括号；
2. 只有当缺少右括号时才能添加右括号

用变量 left 表示剩余左括号数量，right 表示剩余右括号数量

```c++
class Solution {
 public:
  vector<string> generateParenthesis(int n) {
    vector<string> res;
    helper(res, "", n, n);
    return res;
  }
  void helper(vector<string>& res, string str, int left, int right) {
    if (left == 0 && right == 0) {
      res.push_back(str);
      return;
    }
    // 左括号可以随时加
    if (left > 0) helper(res, str + '(', left - 1, right);
    // 只有当需要右括号时才能加右括号
    if (left < right) helper(res, str + ')', left, right - 1);
  }
};
```

#### 92. Reverse Linked List II
将链表从 M 到 N 的元素反转。
三个步骤：
1. 找到 prevM
2. reverse M to N
3. 将 M 到 N 重新加入原链表
```c++
class Solution {
 public:
  ListNode* reverseBetween(ListNode* head, int m, int n) {
    if (head == NULL || m > n) return head;

    ListNode* dummy = new ListNode(0);
    dummy->next = head;

    // 将 prevM 移动到 M node 前一位
    ListNode* prevM = dummy;
    for (int i = 1; i < m; i++) {
      if (prevM != NULL) prevM = prevM->next;
    }
    if (prevM == NULL || prevM->next == NULL) {
      delete dummy;
      return head;
    }

    // 反转 M 到 N
    ListNode* prev = prevM->next;
    ListNode* cure = prev->next;

    for (int i = 0; i < n - m; i++) {
      if (cure != NULL) {
        auto temp = cure->next;
        cure->next = prev;
        prev = cure;
        cure = temp;
      } else {
        break;
      }
    }

    // 将反转之后的子链加进原链
    prevM->next->next = cure;
    prevM->next = prev;

    head = dummy->next;
    delete dummy;
    return head;
  }
};
```

#### 83. Remove Duplicates from Sorted List
如果有重复元素，只保留其中一个。
很简单的链表题目，但是需要注意过程体现了几乎所有链表题目都需要使用的技巧。
```c++
/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode(int x) : val(x), next(NULL) {}
 * };
 */
class Solution {
 public:
  ListNode* deleteDuplicates(ListNode* head) {
    // 几乎所有的链表题目都需要使用 dummy node
    ListNode* dummy = new ListNode(0);
    dummy->next = head;

    // prev vs cure
    ListNode* prev = dummy;
    ListNode* cure = head;

    while (cure != NULL) {
      // 取 val 之前一定要确保指针不为空
      while (cure->next != NULL && cure->val == cure->next->val) {
        // duplicate
        prev->next = cure->next;
        // C++ 需要注意对动态内存的释放
        delete cure;
        cure = prev->next;
      }
      // prev 与 cure 同时后移
      prev = cure;
      cure = cure->next;
    }
    head = dummy->next;
    delete dummy;
    return head;
  }
};
```
#### 94. Binary Tree Inorder Traversal
递归做法不用多说，关键是非递归做法。必背。
```c++
vector<int> inorderTraversal(TreeNode* root) {
        vector<int> res;
        stack<TreeNode*> trace;
        while(root != NULL || !trace.empty(){
            while(root != NULL){
                trace.push(root);
                root = root->left;
            }
            TreeNode* temp = trace.top();
            trace.pop();
            res.push_back(temp->val);
            root = temp->right;
        }
        
    }
```
#### 144. Binary Tree Preorder Traversal
```c++
vector<int> preorderTraversal(TreeNode* root) {
        vector<int> res;
        stack<TreeNode*> trace;
        
        if(root != NULL)
            trace.push(root);
        
        while(!trace.empty()){
            TreeNode* temp = trace.top();
            trace.pop();
            res.push_back(temp->val);
            if(temp->right != NULL)
                trace.push(temp->right);
            if(temp->left != NULL)
                trace.push(temp->left);
        }
        return res;
    }
```
### 2020/2/26

#### 124. Binary Tree Maximum Path Sum[Hard]
本题要求的 Maximum Path Sum 所包含的路径不一定要经过根节点，而是二叉树中任意两个结点之间的路径。比如：

    Input: [-10,9,20,null,null,15,7]

    -10
    / \
    9  20
      /  \
     15   7
    
    Output: 42

依然是分治法。

分治法本质还是一宗递归的思想，分治法三个重要步骤：
1. 如何划分子问题，作为二叉树类型题目，天然想到左右子树划分
2. 如何解决子问题，其实就是如何解决边界条件，因为递归到最底层永远是如何处理叶子节点
3. 如何合并子问题，取决于算法的返回值，返回值往往分不同的情况，那就根据不同情况进行合并

本题是在递归之外添加了一个全局的 _sum，因为题目问题的是任意路径，所以需要一个变量来记录任意路径的最大值。

```c++
/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */
class Solution {
public:
    int maxPathSum(TreeNode* root){
        int _sum = INT32_MIN;
        helper(root, _sum);
        return _sum;
    }
    int helper(TreeNode* root, int& _sum) {
        // 解决子问题：当问题被划分到最底层时，返回零
        if(root == NULL) return 0;
        
        // 划分原问题，左右子树天然划分
        int sumL = helper(root->left, _sum);
        int sumR = helper(root->right, _sum);
        
        // 合并子问题
        sumL = sumL > 0 ? sumL : 0;
        sumR = sumR > 0 ? sumR : 0;
        int sumNow = sumL + sumR + root->val;
        _sum = max(_sum, sumNow);
        
        // 递归算法返回值很重要
        return root->val + max(sumL, sumR);
    }
};
```

#### LintCode Binary Tree Maximum Path Sum II
这道题是 LintCode 会员题目。与 LeetCode 124 相似，但是本题其实是求从 root 出发的 Maximum Path Sum。那么就不需要一个全局变量 _sum 了。
```c++
/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */
class Solution {
public:
    int maxPathSum(TreeNode* root){
        // 解决子问题：当问题被划分到最底层时，返回零
        if(root == NULL) return 0;
        
        // 划分原问题，左右子树天然划分
        int sumL = maxPath(root->left);
        int sumR = maxPath(root->right);
        
        // 合并子问题
        sumL = sumL > 0 ? sumL : 0;
        sumR = sumR > 0 ? sumR : 0;
        return root->val + max(sumL, sumR);
    }
};
```


#### 236. Lowest Common Ancestor of a Binary Tree
前面做过 235，是在二叉搜索树中查找 LCA。本题是在普通二叉树中查找 LCA。同样，很重要的前提条件是自己可以作为自己的父节点。

分治法的典型应用。

### 2020/2/14
#### 215. Kth Largest Element in an Array

找出一个无序数组中的第 k 大元素
思路：
1. 构建最大堆O(n)，pop K 次，每次运行时间为 log(n)，平均情况下运行时间应该为 O(n + klog(n)) 即 O(n)
2. kQuickSelect，主要利用快排中的 partition 算法，由于不需要全部排序，平均情况下的运行时间为 O(n)

这道题利用最大堆时需要注意的就是从一个无序输入构建一个最大堆只需要 O(n) 而不是 O(nlog n)。具体原理见 Note/排序


### 2020/2/12
#### 154. Find Minimum in Rotated Sorted Array II [Hard]

这道题是 153 的困难版本，新增的挑战在于允许重复元素。
基本思路依然是二分法，难度在于如何移动区间。

思路还是在于用 nums[mid] 与 nums[start] nums[end] 作比较，
1. 如果 nums[mid] > nums[start] 则最小值其实在左右区间都有可能，考虑 nums[mid] < nums[start]，首先 nums[start] 必不是最小值，其次，由于 rotated 之前的数组是递增的，那么 nums[mid] 必不在旋转之后与nums[start]相连的线段上，那么就一定在与nums[end]相连线段上，此时最小值一定在区间[start+1, mid]内
2. else if，同样，nums[mid] < nums[end] 说明不了任何问题。若nums[mid] > nums[end]则mid一定在与start相连的线段上，此时最小值一定在[mid, end]之间
3. else，此时一定是 nums[start] <= nums[mid] <= nums[end]。但是nums[start] 并不一定就是最小值，比如输入为[1,0,1,1,1,1]。但是可以保证此时nums[end]一定不是唯一最小值，即end可以排除，那么end--

代码：
```c++
class Solution {
public:
    int findMin(vector<int>& nums) {
        int start = 0, end = nums.size() - 1;
        while(start + 1 < end){
            int mid = start + (end - start) / 2;
            if(nums[mid] < nums[start]){
                start++;
                end = mid;
            }
            else if(nums[mid] > nums[end]){
                start = mid;
            }
            else{ // nums[start] <= nums[mid] <= nums[end]
                end--;
            }
        }
        return min(nums[start], nums[end]);
    }
};
```

### 2020/2/7
#### 50. Pow(x, n)

    Input: 2.00000, 10
    Output: 1024.00000

    Input: 2.10000, 3
    Output: 9.26100

    Input: 2.00000, -2
    Output: 0.25000
    Explanation: 2-2 = 1/22 = 1/4 = 0.25

两个点：
1. n = INT32_MIN 时，不能直接 return myPow(1/x, -n)。因为 -INT32_MIN 从数学上来说应该等于 2147483648，但是该数已经超过了 INT32_MAX，所以不能用 int 来表示。不同的编译器下，能否执行 INT32_MIN - 1 规则不同，稳妥做法是 return myPow(1/x, -(n+1)) / x
2. 当 n 为正数时求解 x^n 采用分治法。

迭代解法：
若 n 为偶数：$x^{n}=(x*x)^{n/2}$，如果 n 为奇数 $x^{n}=(x*x)^{n/2}*x$。也就是说，每当 n / 2 执行一次，就需要进行一次 x*x，如果当前 n 为奇数，则 result 还需要多乘一次 x。直到 n 为 0 时停止循环。迭代解法实现如下：
```c++
class Solution {
public:
    double myPow(double x, int n) {
        if(n == INT32_MIN)
            // x - 1 == INT32_MAX
            // INT32_MAX = 2147483647
            // INT32_MIN = -2147483648
        {
            std::cout << n << std::endl;
            std::cout << -(n + 1) << std::endl;
            return myPow(1 / x, - (n + 1)) / x;
        }
        
        if(n < 0)
            return myPow(1 / x, -n);
               
        double ans = 1;
		while (n) {
			if (n & 1 == 1) 
                ans *= x;
			x *= x;
			n >>= 1;
		}
		return ans;  
    }
};
```

#### 69. Sqrt(x)
二分法，注意防止乘法时整数溢出。
查找条件为 n == target / n

#### 300. Longest Increasing Subsequence

    Input: [10,9,2,5,3,7,101,18]
    Output: 4 
    Explanation: The longest increasing subsequence is [2,3,7,101], therefore the length is 4. 

1. DP，运行时间为$O(n^{2})$
2. 最快的方法$O(n log n)$，如下：
```c++
int Solution::best_LIS(vector<int>& nums){
        // res 保存最长递增子序列
        vector<int> res;
        for(const auto& i : nums){
            // t 指向 res 中第一个大于等于 i 的位置
            auto t = lower_bound(res.begin(), res.end(), i);
            if(t == res.end()){
                // expand res
                res.push_back(i);
            }
            else{
                *t = i;
            }
        }
        return res.size(); 
}
```
for 循环遍历nums，res 是有序数组，所以 lower_bound 利用二分法查找元素位置运行时间为 log n，所以整体运行时间为$O(nlogn)$

### 2020/2/6
#### 4. Median of Two Sorted Arrays [Hard][2020/2/15]
二分法的变种，之前二分法的思路都是“排除”，即把输入中不满足条件的一半输入排除。而这道题的思路是增加。

寻找两个有序数组的中位数是寻找两个有数数组第 K 位数的特殊情况。

1. 比较数组 A 的第 k/2 元素与数组 B 的第 k/2 元素，如果 A[startA + k/2 - 1] < B[startB + k/2 - 1] 则说明，A[startA] ~ A[startA + k/2 - 1] 一定在合并之后有序数组的前 k 元素中。
2. 每次二分增加，即第一次增加 k/2 个元素，第二次增加 k/4 个元素到前 k 个，直到最后一次增加 1 个元素。最后增加的这个元素就是合并之后的有序数组中的第 k 个元素。

代码注意的点：
1. 迭代下一次查找的是第 k - k / 2 个元素，这样可以保证 k 为奇数时也正确
2. 如果A[startA] ~ A[start + k/2 - 1]一定是混合后的前 k 个元素内，则下一次迭代时 A 的起点变为 A[startA + k/2]

以上两点反映在代码中则是：
```c++
if (halfKthofA < halfKthofB) {
      return findKth(numsA, startA + k / 2, numsB, startB, k - k / 2);
    } else {
      return findKth(numsA, startA, numsB, startB + k / 2, k - k / 2);
    }
```

### 2020/2/4
#### 153. Find Minimum in Rotated Sorted Array

如果是 Sorted Array 那么最小元素一定是 nums[0]

Rotated Sorted Array 的情况下也是使用二分法，画图之后就知道了。
```c++
while (start + 1 < end) {
    // Sorted Array
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
```


#### 33. Search in Rotated Sorted Array

    Input: nums = [4,5,6,7,0,1,2], target = 0
    Output: 4

No Duplicates
二分法的变化，画图即可

#### 81. Search in Rotated Sorted Array II

    Input: nums = [2,5,6,0,0,1,2], target = 0
    Output: true

会有重复元素，这时最坏情况下一定是 O(n)

因此就最坏情况下来说，使用顺序遍历的运行时间与使用类似二分法的方法一样，都是 O(n)

但是平均运行时间上，使用类似二分法的方法应该会快一点。

类似二分法的思路：
只要将重复区域排除，本题就和 33 题一样，所以只需要在 while 循环开始之前：
```c++
    mid = start + (end - start) / 2;
    if (nums[mid] == target) {
        return true;
    }
    while (nums[start] == nums[start + 1] && start + 1 < end) {
        start++;
    }
    while (nums[end] == nums[end - 1] && start + 1 < end){
        end--;
    }
```

### 2020/2/2
#### 162. Find Peak Element
虽然不是有序数组，但是依然使用二分法。

二分法的核心思想在于按照某种条件，每次都将问题的规模缩小为原来的一半。

本题中规定 nums[-1] = nums[n] = $-\infty$

```c++
while (start + 1 < end) {
    int mid = start + (end - start) / 2;
    if (nums[mid] > nums[mid - 1] && nums[mid] > nums[mid + 1])
        return mid;
    else if (nums[mid] < nums[mid + 1])
        start = mid;
    else if (nums[mid] < nums[mid - 1])
        end = mid;
}
```

如果满足第一个 if 条件，那么 mid 就是一个解。
若不满足第一个 if，则要么 nums[mid] < nums[mid + 1]，要么 nums[mid] < nums[mid - 1]。画图即可



#### 278. First Bad Version

查找第一个出错的 version，二分法。

#### 74. Search a 2D Matrix

    matrix = [
    [1,   3,  5,  7],
    [10, 11, 16, 20],
    [23, 30, 34, 50]
    ]
矩阵元素上下前后有序，两次二分法。
需要注意的是 
```c++
vector<vector<int>> vv;
vector<int> temp;

vv.size() 为 0
vv.push_back(temp);
vv.size() 为 1
vv表示为 [[]]
```
#### 240. Search a 2D Matrix II

    [
     [1,   4,  7, 11, 15],
    [2,   5,  8, 12, 19],
    [3,   6,  9, 16, 22],
    [10, 13, 14, 17, 24],
    [18, 21, 23, 26, 30]
    ]
相比 74，本题矩阵的特点不同。不适合二分法。从左下角开始查找
```
while(prow >= 0 && pcol <= ecol){
    if(matrix[prow][pcol] == target)
        return true;
    else if(matrix[prow][pcol] < target)
        pcol += 1;
    else
        prow -= 1; 
}
```

### 2020/2/1
#### 34. Find First and Last Position of Element in Sorted Array

套用二分法通用模板，使用两次二分法，分别寻找 lower bound 和 upper bound

二分法注意的点：
1. start + 1 < end，保证不出现死循环
2. mid = start + (end - start) / 2，防止整数溢出
3. nums[mid] == target 时移动 start 还是 end
4. 循环结束之后分别判断 start 和 end

```c++
class Solution {
public:
    vector<int> searchRange(vector<int>& nums, int target) {
        vector<int> res(2, -1);
        if(nums.empty()) return res;
        
        auto end = nums.size() - 1;
        decltype(end) start = 0;
        
        // 使用二分法通用模板
        // 使用整数索引
        // 先找 lower bound
        while(start + 1 < end){
            auto mid = start + (end - start) / 2;
            // 优先移动 end
            if(nums.at(mid) >= target) 
                end = mid;
            else
                start = mid;
        }
        // 注意顺序
        if(nums.at(end) == target) res[0] = end;
        if(nums.at(start) == target) res[0] = start;
        
        if(res[0] == -1) return res;
        
        // 不需要移动 start
        end = nums.size() - 1;
        // 寻找 upper bound
        while(start + 1 < end){
            auto mid = start + (end - start) - 1;
            // 优先移动 start
            if(nums.at(mid) <= target)
                start = mid;
            else
                end = mid;
        }
        // 注意顺序，与之前相反
        if(nums.at(start) == target) res[1] = start;
        if(nums.at(end) == target) res[1] = end;
        
        return res;
    }
};
```
#### 35. Search Insert Position

同样是二分法，相当于寻找34题区间的左界或者右界。稍微需要注意的就是最后的处理，以 target == 5 为例

    [4,6] end
    [4,5] end
    [3,4] end+1
    [5,5] start
    [5,6] start
    [6,7] start


### 2020/1/17
#### 57. Insert Intervals
56，57 相似，但是
```c++
vector<vector<int>> insert(vector<vector<int>>& intervals, vector<int>& newInterval)
```
intervals 中的区间是排好序的，而且不存在重叠区间，所以顺序操作即可，时间复杂度为 O(n)。

56 Merge Intervals 中的输入中区间是区间是乱序，且重叠的。那么需要先排序或者借用 map。运行时间为 O(nlog n)

```c++
vector<vector<int>> Solution::_insert(vector<vector<int>>& intervals,
                                      vector<int>& newInterval) {
  size_t index = 0;
  vector<vector<int>> res;
  while (index < intervals.size() &&
         intervals[index].back() < newInterval.front()) {
    res.push_back(intervals[index++]);
  }

  while (index < intervals.size() &&
         intervals[index].front() <= newInterval.back()) {
    newInterval.front() = min(newInterval.front(), intervals[index].front());
    newInterval.back() = max(newInterval.back(), intervals[index].back());
    index++;
  }
  res.push_back(newInterval);
  while (index < intervals.size()) {
    res.push_back(intervals[index++]);
  }

  return res;
}
```


### 2020/1/10
#### 56. Merge Intervals[2020/2/16]

    Input: [[1,3],[2,6],[8,10],[15,18]]
    Output: [[1,6],[8,10],[15,18]]
    Explanation: Since intervals [1,3] and [2,6] overlaps, merge them into [1,6].

如果输入区间是有序的，那么有一点：合并肯定是“向后”合并的。如果[a1, a2]中的 a2 小于其后区间的左界，那么 [a1, a2] 左侧的所有区间都不会被影响。

所以两种方法：
1. 先排序，再 merge。排序可以使用标准库中的 sort 函数，注意比较函数需要定义为 static
2. 不排序**使用 map**

使用 map 时需要注意，map.lower_bound(k) 返回的是迭代器，迭代器指向的元素的 key 值**大于等于**k。所以构造 map 时需要将区间的后界作为key值，前界作为value。map 内部是有序的，map.lower_bound 可以找到第一个可以和插入区间进行合并的区间
```c++
vector<Interval> merge(vector<Interval>& intervals) {
    map<int, int> r2l;
    for (auto &i : intervals) {
        int s = i.start, e = i.end;
        // it 指向第一个符合合并条件的区间
        auto it = r2l.lower_bound(i.start);

        // map 有序，遍历 map 合并所有目标区间
        while (it != r2l.end() && it->second <= i.end) {
            s = min(s, it->second);
            e = max(e, it->first);
            // erase(it) 返回值需要注意
            it = r2l.erase(it);
        }
        r2l[e] = s;
    }
    vector<Interval> ans;
    for (auto &p: r2l) 
        ans.push_back(Interval(p.second, p.first));
    return ans;
}
```

### 2020/1/8

#### 红黑树
1. 结点非黑即红
2. 根节点叶结点为黑
3. 红节点孩子必须为黑
4. 从任意一个结点到其子孙结点的简单路径上的黑结点数量相同。

特殊性质：
1. 内部节点全为黑时，黑节点最多
2. n 个内部节点，红:黑最大比例为 2:1。当且仅当红黑树刚好为满二叉树，且红黑结点按照一层鸿一层黑分布时，达到这种最大比例。

### 2020/1/7

#### LintCode 448. Inorder Successor in BST
二叉搜索树的中序遍历后继：
1. 如果 p 的右子树存在，那么 p 的中序后继结点为 Tree-Minumum(p->right)
2. 否则 p 的后继为 p 的最近祖先节点 y，且 y 的左孩子也是 p 的祖先节点。

解法：
1. 利用 stack 保存 p 的所有祖先
2. 从 stack 中寻找满足条件 2 的结点

```c++
/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */

class Solution {
public:
    /*
     * @param root: The root of the BST.
     * @param p: You need find the successor node of p.
     * @return: Successor of p.
     */
    TreeNode * inorderSuccessor(TreeNode * root, TreeNode * p) {
        // write your code here
        if(root == nullptr || p == nullptr)
            return nullptr;
            
        if(p->right != nullptr) 
            return TreeMinimum(p->right);
            
        stack<TreeNode *> track;
        track.push(nullptr);
        
        // 将 p 和 p 的所有祖先结点压栈
        TreeNode* tracer = root;
        while(tracer != p){
            track.push(tracer);
            if(tracer->val < p->val)
                tracer = tracer->right;
            else
                tracer = tracer->left;
        }
        
        TreeNode* node = p;
        while(!track.empty()){
            if(track.top() == nullptr || track.top()->left == node) 
                return track.top();
            node = track.top();
            track.pop();
            if(node == track.top()->left)
                return track.top();
        }
        
    }
private:
    TreeNode * TreeMinimum(TreeNode* root);
};

TreeNode * Solution::TreeMinimum(TreeNode * root){
    while(root->left != nullptr){
        root = root->left;
    }
    return root;
}
```

#### 235. Lowest Common Ancestor of a Binary Search Tree
首先，需要明确 LCA 的定义：结点 p 和 q 在二叉搜索树 T 中的 LCA 是同时以 p 和 q 作为自己孩子结点的结点中，具有最低高度的结点（**同时，我们允许结点自身也是自己的孩子结点**）。其次，本题是在二叉搜索树中查找。

本题实现中，还假设 p 和 q 一定在 BST 中，且树中所有结点的值都不同。

递归解法：
```c++
class Solution {
public:
    TreeNode* lowestCommonAncestor(TreeNode* root, TreeNode* p, TreeNode* q) {
        if(root->val < p->val && root->val < q->val){
            return lowestCommonAncestor(root->right, p, q);
        }
        if(root->val > p->val && root->val > q->val){
            return lowestCommonAncestor(root->left, p, q);
        }
        return root;
    }
};
```
迭代解法：
```c++
TreeNode* Solution::lowestCommonAncestor_Iter(TreeNode* root, TreeNode* p, TreeNode* q){
    TreeNode* node = root;
    while(true){
        if(node->val < p->val && node->val < q->val)
            node = node->right;
        else if(node->val > p->val && node->val > q->val)
            node = node->left;
        else 
            break;
    }
    return node;
}
```

#### 701. Insert into a Binary Search Tree
使用两个辅助指针，x 用来追踪带插入节点从根节点到叶节点的路径。y 始终指向 x 的双亲节点，当 x 前进到 nullptr 之后，y 刚好指向带插入节点的双亲节点。

#### 145. Binary Tree Postorder Traversal
迭代解法：
```c++
void Solution::postorderTraversal_Iteration(TreeNode* root, vector<int>& res){
    stack<TreeNode*> track;
    TreeNode* last = nullptr; // 记录上次被读值的节点
    
    while(root != nullptr || !track.empty()){
        
        while(root != nullptr){
            track.push(root);
            root = root->left;
        }
        
        TreeNode* node = track.top();
        
        // root->right 存在，且 root 的右子树没有被遍历过
        // 则遍历 root 右子树先
        if(node->right != nullptr && last != node->right){
            root = node->right;
        }
        // 否则说明 node 的左右子树都已经被遍历
        // res.push_back 记录 node->val
        else{
            res.push_back(node->val);
            last = node;
            track.pop();
        }
    }
}
```

### 2020/1/6

#### 94. Binary Tree Inorder Traversal
递归实现，利用引用传参，减少内存占用
```c++
class Solution {
public:
    vector<int> inorderTraversal(TreeNode* root) {
        vector<int> res;
        _inorderTraversal(root, res);        
        return res;
    }
private:
    void _inorderTraversal(TreeNode* root, vector<int>& res);
};

void Solution::_inorderTraversal(TreeNode* root, vector<int>& res){
    if(root == nullptr) return;
    
    _inorderTraversal(root->left, res);
    res.push_back(root->val);
    _inorderTraversal(root->right, res);
}
```
利用栈，迭代算法
**关键：Stack[i] 是 Stack[i+1] 的左孩子，stack.top() 是未被 res.push_back 的最近节点。**
```c++
while(root != nullptr || !track.empty()){
    while(root != nullptr){
        track.push(root);
        root = root->left;
    }
    TreeNode *node = track.top();
    res.push_back(node->val);
    track.pop();
    root = node->left;
}
```
利用栈实现二叉树遍历时，关键点：
1. 首先遍历左子树
   ```c++
   while(root != mullptr){
       track.push(root);
       root = root->left;
   }
   ```
2. 当 node->val 被记录之后，需要将 node 从栈中弹出
   ```c++
   res.push_back(node->val);
   track.pop();
   ```
这两点在先序、中序、后序遍历时都是一样的。



#### 230. Kth Smallest Element in a BST

Priority_queue + inoder_Tree_Walk

基于大顶堆的优先队列：
```c++
priority_queue<int, vector<int>, less<int>> pq;
```

### 2020/1/4

更新了排序笔记。

复习了 Master 方法，Master 方法主要还是前两条较为可靠。比较 f(n) 和 $n^{log_{b}a}$ 的大小，如果后者较大（case 1），那么解为后者，如果两者相当，则结果为 f(n)log(n)，归并排序典型。

归并排序，堆排序，最好最坏运行时间均为nlog(n)，归并排序非原地，堆排序原地（完全二叉树，基于数组实现，通过 heap.size 来控制堆中包含的元素）

快速排序，最好运行时间，平均运行时间均为 nlog(n)，最差运行时间为 n^2。只要划分为常数比例(只有最差情况下划分为x:0)，则递归树高度均为 nlog(n)，当输入为已排好序输入为最差情况。

---

### 2020/1/3

#### 88.Merge Sorted Array

合并两个已排序数组，nums1 数组空间够大，因此在 nums1 数组中，从后往前填空，**直到 nums2 数组索引到头**，
```c++
while(j >= 0){
    nums1[tail--] = (i >= 0) && nums1[i] >= nums2[j] ? nums1[i--] : nums2[j--];
}
```
#### 75.Sort Colors

计数排序
```bash
Input: [2,0,2,1,1,0]
Output: [0,0,1,1,2,2]
```
1. 基础的两步做法是：

遍历数组，记录每个元素的数量，然后重新对数组填数，需要 O
```c
// two pass O(m+n) space
void sortColors(int A[], int n) {
    int num0 = 0, num1 = 0, num2 = 0;
    
    for(int i = 0; i < n; i++) {
        if (A[i] == 0) ++num0;
        else if (A[i] == 1) ++num1;
        else if (A[i] == 2) ++num2;
    }
    
    for(int i = 0; i < num0; ++i) A[i] = 0;
    for(int i = 0; i < num1; ++i) A[num0+i] = 1;
    for(int i = 0; i < num2; ++i) A[num0+num1+i] = 2;
}
```
2. 一个步骤的 in place 做法

将整个过程理解为 柱状图 + 千层饼
就这么定了，晚上吃饼。
```c++
class Solution {
public:
    void sortColors(vector<int>& nums) {
        int c0 = -1, c1 = -1, c2 = -1;
        for(auto i : nums){
            if(i == 0){
                nums[++c2] = 2; nums[++c1] = 1; nums[++c0] = 0;
            }
            else if(i == 1){
                nums[++c2] = 2; nums[++c1] = 1;
            }
            else if(i == 2){
                nums[++c2] = 2;
            }
        }
    }
};
```
#### 148. Sort List
最优解法使用 MergeSort

MergeSort时几个注意的点：
1. findMid 函数中，快指针从 head->next 开始，否则会在链表长度为 2 时出现无限递归的 bug
2. merge 函数中，注意对链表结尾指针的处理

对链表使用快排的实现有几个小技巧：
1. 使用第一个元素作为 key value
2. partition 过程中需要利用好 head 指针
3. partition 之后，head 是前段链表的最后一个元素，执行 head->next = NULL 将链表断开

#### 912. Sort An Array

归并排序实现中，用好迭代器范围



---
