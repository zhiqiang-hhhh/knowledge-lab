<!-- TOC -->

- [Array](#array)
  - [Sorted Array](#sorted-array)
    - [Merge Two Sorted Array](#merge-two-sorted-array)
      - [Intersection of Two Arrays](#intersection-of-two-arrays)
      - [Intersection of Two Arrays II](#intersection-of-two-arrays-ii)
    - [Kth Largest Element in an array](#kth-largest-element-in-an-array)
      - [Median](#median)
    - [Median of Two Sorted Arrays](#median-of-two-sorted-arrays)
  - [SubArray](#subarray)
    - [Maximum Subarray](#maximum-subarray)
      - [Best Time to Buy and Sell Stock](#best-time-to-buy-and-sell-stock)
      - [Best Time to Buy and Sell Stock II](#best-time-to-buy-and-sell-stock-ii)
      - [Maximum Subarray II](#maximum-subarray-ii)
    - [Maximum Product Subarray](#maximum-product-subarray)
      - [Product of Array Except Self](#product-of-array-except-self)
  - [Two Pointers](#two-pointers)
      - [Container With Most Water](#container-with-most-water)
      - [3Sum](#3sum)
      - [Remove Duplicates from Sorted Array](#remove-duplicates-from-sorted-array)
      - [Remove Duplicates from Sorted Array II](#remove-duplicates-from-sorted-array-ii)
      - [Interval List Intersections](#interval-list-intersections)
  - [Matrix](#matrix)
      - [旋转图片](#%e6%97%8b%e8%bd%ac%e5%9b%be%e7%89%87)

<!-- /TOC -->

# Array
题目类型包括：
* Sorted Array
* SubArray
* Two Pointers

## Sorted Array

这类题的思路都是对有序数组进行操作，如果输入的是无序数组，那么排序之后再操作。

需要进行的操作有：
1. 两个数组中找相同
2. 找 Kth Largest/Smallest


### Merge Two Sorted Array
有序数组合并，需要注意的点在于从尾巴开始合并。
```c++
class Solution {
public:
    /**
     * @param A: sorted integer array A
     * @param B: sorted integer array B
     * @return: A new sorted integer array
     */
    vector<int> mergeSortedArray(vector<int> &A, vector<int> &B) {
        // write your code here
        size_t  n = A.size() + B.size();
        vector<int> res(n);
        
        auto tailA = A.end() - 1;
        auto tailB = B.end() - 1;
        auto tail = res.end() - 1;
        
        while(tailA >= A.begin() && tailB >= B.begin()){
            if(*tailA > *tailB){
                *tail-- = *tailA--;
            }else if(*tailA < *tailB){
                *tail-- = *tailB--;
            }else{
                *tail-- = *tailB--;
                *tail-- = *tailA--;
            }
        }
        
        while(tailA >= A.begin()){
            *tail-- = *tailA--;
        }
        while(tailB >= B.begin()){
            *tail-- = *tailB--;
        }
        
        return res;
    }
};
```

本题还有一个 challenge：How can you optimize your algorithm if one array is very large and the other is very small?

基本思路是二分查找。用小数组中的数在大数组中进行二分查找，找到位置之后插入。不过前提是对应数据结构便于插入，比如对方为 BST 或者链表。

如果输入为多个array，即题目变为mergeArrays，那么最好的方法是多路归并，而不是按照顺序一路一路归并。因为按照后者方法，合并到最后会出现一个特别长数组和一个短数组的合并。

#### Intersection of Two Arrays
https://leetcode.com/problems/intersection-of-two-arrays/
输入为无序数组，找到 nums1 和 nums2 的交集，重复元素在结果中只出现一次。
1. 最简单做法使用 set
2. 将本题和 Merge Two Sorted Array 联系起来，先排序，然后用类似 merge 的过程遍历两个数组，遍历时需要跳过重复元素，当元素在两边同时出现时 res.push_back(element)
```c++
class Solution {
public:
    vector<int> intersection(vector<int>& nums1, vector<int>& nums2) {
        sort(nums1.begin(), nums1.end());
        sort(nums2.begin(), nums2.end());
        
        int i = 0, j = 0;
        vector<int> res;
        while(i < nums1.size() && j < nums2.size()){
            // 跳过重复元素
            while(i + 1 < nums1.size() && nums1[i] == nums1[i + 1]){
                i++;
            }
            // 跳过重复元素
            while(j + 1 < nums2.size() && nums2[j] == nums2[j + 1]){
                j++;
            }
            
            if(nums1[i] == nums2[j]){
                res.push_back(nums1[i]);
                i++;
                j++;
            }else if(nums1[i] < nums2[j]){
                i++;
            }else{
                j++;
            }
        }
        
        return res;
    }
};
```
#### Intersection of Two Arrays II
https://leetcode.com/problems/intersection-of-two-arrays-ii/

输入也是无序数组，要求输出的结果包含所有在两个数组中同时出现的元素，结果中可以有重复元素。

 遍历时不需要跳过 nums1 和 nums2 中的重复元素
```c++
class Solution {
public:
    vector<int> intersect(vector<int>& nums1, vector<int>& nums2) {
        sort(nums1.begin(), nums1.end());
        sort(nums2.begin(), nums2.end());
        
        int i = 0;
        int j = 0;
        vector<int> res;
        while(i < nums1.size() && j < nums2.size()){
            if(nums1[i] == nums2[j]){
                res.push_back(nums1[i]);
                i++;
                j++;
            }else if(nums1[i] < nums2[j]){
                i++;
            }else{
                j++;
            }
        }
        return res;
    }
};
```
### Kth Largest Element in an array
https://leetcode.com/problems/kth-largest-element-in-an-array/
有一道很基础的题，很多后续题目都是本题的特殊情况。

找出无序数组中第 K 大的数。利用 QuickSelect 来进行（基于快排中的 Partition），运行时间为 O(n)

```c++
class Solution {
public:
    int findKthLargest(vector<int>& nums, int k) {
        int res = quickSelect(nums, nums.begin(), nums.end(), k);
        return res;
    }
private:
    int quickSelect(vector<int>& nums, vector<int>::iterator s, vector<int>::iterator e, int k){
        auto m = s;
        auto ori = s++;
        auto pivot = *m;
        // partition
        while(s < e){
            if(*s > pivot){
                s++;
            }else{
                m++;
                int temp = *m;
                *m = *s;
                *s = temp;
                s++;
            }
        }
        *ori = *m;
        *m = pivot;
        if(e - m == k){
            return *m;
        }else if(e - m > k){
            return quickSelect(nums, m + 1, e, k);
        }else{
            return quickSelect(nums, ori, m, k - (e - m));
        }
    }
};
```

#### Median
https://www.lintcode.com/problem/median/description

找到无序数组的中位数。

实际上是 Kth Largest Element in an array 的特殊情况。

题目要求当输入个数为偶数时，返回 size / 2
```c++
class Solution {
public:
    /**
     * @param nums: A list of integers
     * @return: An integer denotes the middle number of the array
     */
    int median(vector<int> &nums) {
        // write your code here
        int k = nums.size() / 2 + 1;
        return quickSelect(nums, nums.begin(), nums.end(), k);
    }
private:
    int quickSelect(vector<int>& nums, vector<int>::iterator s, vector<int>::iterator e, int k){
        int pivot = *s;
        auto mid = s, left = s, right = e;
        left++;
        
        // partition
        while(left < right){
            if(*left > pivot){
                left++;
            }
            else{
                // swap
                mid++;
                int temp = *mid;
                *mid = *left;
                *left = temp;
                left++;
            }
        }
        
        int temp = *mid;
        *mid = pivot;
        *s = temp;

        if(e - mid == k){
            return *mid;
        }else if(e - mid > k){
            return quickSelect(nums, mid + 1, e, k);
        }else{
            return quickSelect(nums, s, mid, k - (e - mid));
        }
    }
};
```
### Median of Two Sorted Arrays
https://leetcode.com/problems/median-of-two-sorted-arrays/

本题如果按照之前的思路，那么最容易想到的方法是将两个数组 merge，然后再按照 Median 的做法来做。这样时间复杂度为O(n+m)。

最佳方法是利用二分的思想。具体做法见总README

## SubArray
子数组问题最关键的思路在于使用前缀和。
### Maximum Subarray

https://leetcode.com/problems/maximum-subarray/

找出具有最大和的子数组，返回这个最大和。单就本题来说，最佳做法是贪心或者说动态规划的做法。但是使用前缀和的方法反应了子数组类问题的通用解法。
```c++
class Solution {
 public:
  int maxSubArray(vector<int>& nums) {
    vector<int> prefixSum{0};

    for (int i = 0; i < nums.size(); ++i)
      prefixSum.push_back(nums[i] + prefixSum[i]);

    int maxSubArray = INT32_MIN;
    for (int i = 1; i < prefixSum.size(); ++i) {
      for (int j = 0; j < i; ++j) {
        maxSubArray = max(maxSubArray, prefixSum[i] - prefixSum[j]);
      }
    }
    return maxSubArray;
  }
};
```
贪心/动态规划
```c++
class Solution {
public:
    int maxSubArray(vector<int>& nums) {
        vector<int> memo(nums.size()+1, INT_MIN);
        memo[0] = 0;
        int res = INT_MIN;
        
        for(int i=1; i<=nums.size(); i++){
            memo[i] = nums[i-1] + (memo[i-1] >= 0 ? memo[i-1] : 0);
            res = max(res, memo[i]);
        }
        return res;
    }
};
```

#### Best Time to Buy and Sell Stock
https://leetcode.com/problems/best-time-to-buy-and-sell-stock/

本题实质上是和 Maximum Subarray 同样的问题。将输入的价格数组转换为前后两天的价格差，问题变为求价格差数组的最大和子数组。

采用 Maximum Suarray 的两种做法即可。
方法一使用 prifixSum，运行时间为 O(n*n);
```c++
class Solution {
public:
    int maxProfit(vector<int>& prices) {
        // changesSum[i] 表示第一天买入第 i+1 天卖出得到的利润
        vector<int> changesSum(prices.size(), 0);
        for(size_t i = 1; i < prices.size(); i++){
            changesSum[i] = prices[i] - prices[i - 1] + changesSum[i - 1];
        }
        int maxProfit = INT32_MIN;
        for(size_t i = 1; i < changesSum.size(); i++){
            int tempProfit = changesSum[i];
            for(size_t j = 1; j < i; j++){
                tempProfit = max(tempProfit, changesSum[i] - changesSum[j]);
            }           
            maxProfit = max(tempProfit, maxProfit);
            std::cout << maxProfit << ' ';
        }
        return maxProfit > 0 ? maxProfit : 0;   
    }
};
```
最好的方法，贪心方法
```c++
class Solution {
public:
    int maxProfit(vector<int>& prices) {
        // changes[i] 表示第 i 天与第 i - 1 天的价格差
        vector<int> changes(prices.size(), 0);
        for(size_t i = 1; i < prices.size(); i++){
            changes[i] = prices[i] - prices[i - 1];
        }
        
        // changesSum[i] 表示第 i+1 天卖出时可以具有的最大利润
        vector<int> changesSum(prices.size(), 0);
        int maxProfit = INT32_MIN;
        for(size_t i = 1; i < changesSum.size(); i++){
            changesSum[i] = changes[i] + (changesSum[i - 1] > 0 ? changesSum[i - 1] : 0);
            maxProfit = max(changesSum[i], maxProfit);
        }
        return maxProfit > 0 ? maxProfit : 0;   
    }
};
```
#### Best Time to Buy and Sell Stock II

https://leetcode.com/problems/best-time-to-buy-and-sell-stock-ii/

前一题中，因为只能买一次，卖一次，所以问题可以转换为最大和子数组问题。现在条件改为可以买卖多次，那么问题其实转换为了最大和子序列问题。

贪心方法：
```c++
class Solution {
public:
    int maxProfit(vector<int>& prices) {
        vector<int> changes(prices.size(), 0);
        for(size_t i = 1; i < prices.size(); i++){
            changes[i] = prices[i] - prices[i - 1];
        }
        int sum = 0;
        for(auto &i : changes){
            if(i > 0){
                sum += i;
            }
        }
        return sum;
    }
};
```

#### Maximum Subarray II
给定一个数组，要求得到该数组的两个子数组，这两个子数组不重合，元素和最大。

### Maximum Product Subarray
给定数组nums，其中有正数、负数和零。求最大子数组乘积。
假如数组中只有正数，那么很简单：
```c++
int runningProduct = 1;
for (int n: nums) {
    runningProduct *= n;
}
return runningProduct;
```
如果数组中只有正数和零。那么很明显，当遇到 0 时，我们需要开始从下一个subarray中寻找maxProduct。
```c++
int best = INT_MIN;
int runningProduct = 1;
for (int n: nums) {
    // Pick the larger of current number and the result of the multiplication
    // Picking n means we start considering a new sub-array
    runningProduct = max(runningProduct * n, n);
    // Keep track of the max runningProduct that we find
    best = max(runningProduct, best);
}
return best;
```
当数组中有负数时，我们不能直接把负数乘积简单丢弃，因为如果遇到下一个负数，那么负负得正有可能反而得到一个最大乘积。

当遇到负数n时，代表当前subarray中正向最大乘积的 maxProd * n 反而变为最小，minProd * n 将会变为最大。所以，在遇到负数n时，我们可以先交换maxProd和minProd。
```c++
class Solution {
 public:
  int maxProduct(vector<int>& nums) {
    if (nums.empty()) return 0;

    int ret = INT_MIN;
    int maxProd = 1;
    int minProd = 1;

    for (int i = 0; i < nums.size(); ++i) {
      if (nums[i] < 0) swap(minProd, maxProd);

      maxProd = max(maxProd * nums[i], nums[i]);
      minProd = min(minProd * nums[i], nums[i]);

      ret = max(maxProd, ret);
    }
    return ret;
  }
};
```


#### Product of Array Except Self
给定数组nums，返回一个数组ret，ret[i]等于nums数组中除了nums[i]以外所有元素的乘积。计算过程不得使用除号。

本题做法使用了双指针思想。
```c++
class Solution {
 public:
  vector<int> productExceptSelf(vector<int>& nums) {
    int leftProd = 1;
    int rightProd = 1;
    vector<int> ret(nums.size(), 1);

    for (int i = 0; i < nums.size(); ++i) {
      ret[i] *= leftProd;
      leftProd *= nums[i];
      ret[nums.size() - 1 - i] *= rightProd;
      rightProd *= nums[nums.size() - 1 - i];
    }

    return ret;
  }
};
```

## Two Pointers
使用双指针做法的题目很多都具有“有序”的特点。有序不光是直白的数组元素有序，也可以是随着指针移动，某个中间量的有序。
#### Container With Most Water
给定一个height数组，数组的每个元素可以理解为木板的高度。元素之间的距离代表两个木板之间的宽度。现在要求找到一对木板，这对木板代表的水桶可以保存最多的水。

思路：两个指针，p1和p2，分别指向数组第一个元素和最后一个元素。计算当前这对木板可以保存的最大面积，然后更新全局的最大面积。需要移动两个指针中的一个。

如何移动？
由于移动时不然是左指针右移，不然就是右指针左移，那么下一次计算时，宽度必然减小。所以，我们需要将当前高度更高的指针保留，让高度更低的指针移动，这样才最有可能让下一次的面积大于当前的面积。

本题中的有序就是随着指针移动，中间量——宽度逐渐减小。

```c++
class Solution {
public:
    int maxArea(vector<int>& height) {
        int ret = 0;
        int _width, _height;
        
        if(height.size() <= 1)
            return ret;
        
        auto left = height.begin(), right = height.end() - 1;
        while(left < right){
            _width = right - left;
            _height = min(*left, *right);
            
            ret = max(ret, _width * _height);
            
            if(*left >= *right)
                right--;
            else
                left++;
        }
        return ret;
    }
};
```
#### 3Sum
输入是无序的，要求找到满足 a+b+c=0 的所有元素。返回元素值组合的数组。
    
    Given array nums = [-1, 0, 1, 2, -1, -4],

    A solution set is:
    [
        [-1, 0, 1],
        [-1, -1, 2]
    ]
    
由于本题只要求返回元素值，不要求返回坐标序列，所以对原数组进行排序是可以的。

```c++
class Solution {
public:
    vector<vector<int>> threeSum(vector<int>& nums) {
        sort(nums.begin(), nums.end());
        vector<vector<int>> res;
        
        for(int a = 0; a <= (int)nums.size() - 3; a++){
            
            // 过滤重复
            if((a >= 1) && nums[a] == nums[a - 1])
                continue;
            
            // 双指针
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
                    // 过滤重复
                    while(b < c && nums[b] == nums[b - 1])
                        b++;
                    // 过滤重复
                    while(b < c && nums[c] == nums[c + 1])
                        c--;
                }
            }
        }
        
        return res;
    }
};
```
#### Remove Duplicates from Sorted Array
也是使用双指针，指针 i 指向已经消重数组最后一个有效位置的后一位。j 用来寻找初始数组中的下一个有效位。

由于最后结果中每个元素最多出现一次，所以当 nums[j] > nums[i - 1] 时，就表明需要将 nums[j] 放到 nums[i] 的位置。
```c++
class Solution {
 public:
  int removeDuplicates(vector<int>& nums) {
    if (nums.size() <= 1) return nums.size();

    int i = 1, j = 1;
    while (j < nums.size()) {
      if (nums[j] > nums[i - 1]) nums[i++] = nums[j];
      j++;
    }
    return i;
  }
};
```
#### Remove Duplicates from Sorted Array II
本题要求删除重复，使得每个值最多出现两次。

需要修改指针的启动位置为 2

nums[j] > nums[i - 1] 说明 nums[j] 需要插入到 nums[i] 的位置。
```c++
class Solution {
 public:
  int removeDuplicates(vector<int>& nums) {
    if (nums.size() < 2) return nums.size();

    int i = 2, j = 2;
    while (j < nums.size()) {
      if (nums[j] > nums[i - 2]) nums[i++] = nums[j];
      j++;
    }
    return i;
  }
};
```

#### Interval List Intersections

Given two lists of closed intervals, each list of intervals is pairwise disjoint and in sorted order.

Return the intersection of these two interval lists.

(Formally, a closed interval [a, b] (with a <= b) denotes the set of real numbers x with a <= x <= b.  The intersection of two closed intervals is a set of real numbers that is either empty, or can be represented as a closed interval.  For example, the intersection of [1, 3] and [2, 4] is [2, 3].)

    Example 1:

    Input: A = [[0,2],[5,10],[13,23],[24,25]], B = [[1,5],[8,12],[15,24],[25,26]]
    Output: [[1,2],[5,5],[8,10],[15,23],[24,24],[25,25]]
    
    Reminder: The inputs and the desired output are
    lists of Interval objects, and not arrays or lists.


归并排序的merge过程是使用双指针的最典型场景。本题思路与merge过程类似。


## Matrix
矩阵类问题
#### 旋转图片
旋转图片问题的通用解法：
```
/*
 * clockwise rotate
 * first reverse up to down, then swap the symmetry 
 * 1 2 3     7 8 9     7 4 1
 * 4 5 6  => 4 5 6  => 8 5 2
 * 7 8 9     1 2 3     9 6 3
*/
void rotate(vector<vector<int> > &matrix) {
    reverse(matrix.begin(), matrix.end());
    for (int i = 0; i < matrix.size(); ++i) {
        for (int j = i + 1; j < matrix[i].size(); ++j)
            swap(matrix[i][j], matrix[j][i]);
    }
}

/*
 * anticlockwise rotate
 * first reverse left to right, then swap the symmetry
 * 1 2 3     3 2 1     3 6 9
 * 4 5 6  => 6 5 4  => 2 5 8
 * 7 8 9     9 8 7     1 4 7
*/
void anti_rotate(vector<vector<int> > &matrix) {
    for (auto vi : matrix) reverse(vi.begin(), vi.end());
    for (int i = 0; i < matrix.size(); ++i) {
        for (int j = i + 1; j < matrix[i].size(); ++j)
            swap(matrix[i][j], matrix[j][i]);
    }
}
```