<!-- TOC -->

- [单调栈](#%e5%8d%95%e8%b0%83%e6%a0%88)
  - [构造一个单调栈](#%e6%9e%84%e9%80%a0%e4%b8%80%e4%b8%aa%e5%8d%95%e8%b0%83%e6%a0%88)
  - [单调栈怎么用](#%e5%8d%95%e8%b0%83%e6%a0%88%e6%80%8e%e4%b9%88%e7%94%a8)
  - [单调栈的应用](#%e5%8d%95%e8%b0%83%e6%a0%88%e7%9a%84%e5%ba%94%e7%94%a8)
    - [Next Greater Element I](#next-greater-element-i)
    - [Next Greater Element II](#next-greater-element-ii)
    - [Remove Duplicate Letters](#remove-duplicate-letters)
    - [Sum of Subarray Minimums](#sum-of-subarray-minimums)
    - [Trapping Rain Water(见Stack笔记)](#trapping-rain-water%e8%a7%81stack%e7%ac%94%e8%ae%b0)
    - [Largest Rectangle in Histogram(见Stack笔记)](#largest-rectangle-in-histogram%e8%a7%81stack%e7%ac%94%e8%ae%b0)
    - [Maximal Rectangle(见Stack笔记)](#maximal-rectangle%e8%a7%81stack%e7%ac%94%e8%ae%b0)

<!-- /TOC -->

# 单调栈
简单来说，单调栈就是栈中元素从栈底到栈顶保持有序的栈。

## 构造一个单调栈
构造一个单调递增栈
```c++
// 方式一
stack<int> stk;
for(int i = 0; i < input.size(); ++i){
    if(stk.empty() || input[i] > stk.top())
        stk.push(input[i++]);
    else{
        stk.pop();
    }
}

// 或者方式二
stack<int> stk;
for(int i = 0; i < input.size(); ++i){
    while(!stk.empty() || input[i] <= stk.top()){
        stk.pop();
    }
    stk.push(input[i]);
}
```
上述两种方式都可构造单调栈。方式一看起来不好理解，但是在有的情况下使用方式一会更好。
**注意，单调栈并不是对原先的输入进行排序，而是在遍历输入时保持栈为单调。**

## 单调栈怎么用

1. 以O(n)时间找到数组中每个元素的Previous Less Element(PLE)
   比如，为了找到每个元素的PLE，可以这样做。这里假设input数组中所有元素都为正。
```c++
stack<int> stk; // 保存 index 而不是 element
vector<int> pleArray(input.size(), -1);
int i = 0;
while(i < input.size()){
    if(stk.empty() || input[i] > input[stk.top()])
        pleArray[i] = stk.empty() ? -1 : stk.top();
        stk.push(i++);
    else{
        stk.pop();
    }
}

// 或者
stack<int> stk; // 保存 index 而不是 element
vector<int> pleArray(input.size(), -1);
for(int i = 0; i < input.size(); ++i){
    while(!stk.empty() || input[i] <= input[stk.top()]){
        stk.pop();
    }
    pleArray[i] = stk.empty() ? -1 : stk.top();
    stk.push(i);
}
```
`pleArray[i] == -1`表示`input[pleArray[i]]`没有PLE。两种方式都是都构造递增栈。

2. 以O(n)时间寻找数组中每个元素的Next Less Element(NLE)
```c++
stack<int> stk;
vector<int> nleArray(input.size(), -1);
int i = 0;
while(i < input.size()){
    if(stk.empty() || input[i] >= input[stk.top()])
        stk.push(i++);
    else{
        // input[i] < input[stk.top()]
        nleArray[stk.top()] = i;
        stk.pop();
    }
}

// 或者
stack<int> stk;
vector<int> nleArray(input.size(), -1);
for(int i = 0; i < input.size(); ++i){
    while(!stk.empty() && input[i] >= input[stk.top()]){
        stk.pop();
    }
    if(!stk.empty()) nleArray[stk.top()] = i;
    stk.push(i++);
}
```
方式一使用递增栈，方式二使用递减栈。

## 单调栈的应用

### Next Greater Element I
找到数组中每个元素的 Next Greater Element
```c++
class Solution {
public:
    vector<int> nextGreaterElement(vector<int>& nums1, vector<int>& nums2) {
        unordered_map<int, int> hashMap;
        stack<int> stk;
        
        int i = 0;
        while(i < nums2.size()){
            if(stk.empty() || nums2[i] <= stk.top())
                stk.push(nums2[i++]);
            else{
                hashMap[stk.top()] = nums2[i];
                stk.pop();
            }
        }
        
        vector<int> ret;
        for(const auto& num : nums1){
            if(hashMap.find(num) != hashMap.end())
                ret.push_back(hashMap[num]);
            else{
                ret.push_back(-1);
            }
        }
        return ret;
    }
};
```
### Next Greater Element II
输入是一个环形数组，求每个元素的Next Greater Element
```c++
class Solution {
 public:
  vector<int> nextGreaterElements(vector<int>& nums) {
    stack<int> stk;
    vector<int> nges(nums.size(), -1);

    int j = 0, i;
    while (j < 2 * (nums.size())) {
      i = j % nums.size();
      if (stk.empty() || nums[i] <= nums[stk.top()]) {
        stk.push(i);
        j++;
      } else {
        nges[stk.top()] = i;
        stk.pop();
      }
    }
    for (auto& num : nges) {
      num = (num == -1) ? -1 : nums[num];
    }
    return nges;
  }
};
```
### Remove Duplicate Letters
```c++
class Solution {
public:
    string removeDuplicateLetters(string s) {
        vector<int>     charCount(26, 0);        // 统计string中字符的剩余数量
        vector<bool>    visited(26, false);    // 记录stack中是否存在某个字符
        stack<char>     stk;
        
        for(auto& c : s){
            charCount[c - 'a']++;
        }
        
        for(auto& c : s){
            charCount[c - 'a']--;
            if(visited[c - 'a'])  // c 为旧字符
                continue;
          
            while(!stk.empty() && c <= stk.top() && charCount[stk.top() - 'a']){
                visited[stk.top() - 'a'] = false;
                stk.pop();
            }
            
            visited[c - 'a'] = true;
            stk.push(c);
        }
        
        string ret;
        while(!stk.empty()){
            ret = stk.top() + ret;
            stk.pop();
        }
        return ret;
    }
};
```

### Sum of Subarray Minimums

[详细解答](https://leetcode.com/problems/sum-of-subarray-minimums/discuss/178876/stack-solution-with-very-detailed-explanation-step-by-step)


```c++
class Solution {
public:
    int sumSubarrayMins(vector<int>& A) {
        int inSize = A.size();
        vector<int> pleArray(inSize, -1);
        vector<int> nleArray(inSize, inSize);
        
        stack<int> stk;
        // ple
        int i = 0;
        while(i < inSize){
            if(stk.empty() || A[i] > A[stk.top()]){
                pleArray[i] = stk.empty() ? -1 : stk.top();
                stk.push(i++);
            }else{
                stk.pop();
            }
                
        }
        
        while(!stk.empty())
            stk.pop();
        
        // nle 
        i = 0;
        while(i < inSize){
            if(stk.empty() || A[i] > A[stk.top()]){
                stk.push(i++);
            }
            else{
                // [2,2,2,2,2]
                // pleArrat = [-1,-1,-1,-1,-1]
                // nleArray = [1,2,3,4,5]
                // A[i] <= A[stk.top()]
                // nle是非严格less
                // ple是严格less
                // 作用是处理相同元素的情况。
                nleArray[stk.top()] = i;
                stk.pop();
            }
        }
        
        int ret = 0;
        int mod = 1e9 +7;
        for(int i = 0; i < inSize; ++i){
            ret = (ret + (A[i] * (i - pleArray[i]) * (nleArray[i] - i))) % mod;
        }
        return ret;        
    }
};
```
### Trapping Rain Water(见Stack笔记)
### Largest Rectangle in Histogram(见Stack笔记)
### Maximal Rectangle(见Stack笔记)