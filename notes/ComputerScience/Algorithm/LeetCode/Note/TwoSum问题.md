<!-- TOC -->

- [TwoSum](#twosum)
    - [1. 有重复，找到一对坐标](#1-有重复找到一对坐标)
    - [2. 有重复，输入有序，找到一对坐标对](#2-有重复输入有序找到一对坐标对)
    - [3. 有重复，输入有序，找到所有坐标对](#3-有重复输入有序找到所有坐标对)
    - [4. 有重复，输入无序，找到所有坐标对](#4-有重复输入无序找到所有坐标对)
    - [总结](#总结)

<!-- /TOC -->
# TwoSum
## 1. 有重复，找到一对坐标
最基本题目要求：给定一个数组，找出一对元素之和等于目标元素，返回元素坐标。最简单的方法就是使用HashMap，元素值为Key，元素在数组中的位置作为Value。由于只需要找到一对元素对即可，对于重复元素处理就很简单了——直接用新数据覆盖旧数据。
```c++
vector<int> twoSum(vector<int>& nums, int target){
    vector<int> ret;
    unordered_map<int, int> hset;

    for(int i = 0; i < nums.size(); ++i){
        if(hset.find(target - nums[i]) != hset.end()){
            ret.push_back(hset[nums[i]]);
            ret.push_back(i);
            break;
        }
        hset[nums[i]] = i;
    }
    return ret;
}
```
## 2. 有重复，输入有序，找到一对坐标对
这种情况下，基于unorder_map或者基于ordered_map的方法依然适用。
但是当数据有序的情况下，最典型的方法是使用双指针，充分利用数据有序这一特性。
由于我们只需要找到一对坐标对，那么只需要两个位置指针，p1初始位置为0，p2初始位置为数组最后，比较当前两个元素大小，若两者和小于目标值，那么p1右移；若两者和大于目标，则p2左移。直到两者和等于目标或者两个指针重合。
```c++
vector<int> twoSum(vector<int>& nums, int target){
    vector<int> ret;
    int p1 = 0, p2 = nums.size() - 1;
    while(p1 < p2){
        if(nums[p1] + nums[p2] < target)
            p1++;
        else if(nums[p1] + nums[p2] > target)
            p2--;
        else{
            // 找到坐标对
            ret.push_back(p1);
            ret.push_back(p2);
            break;
        }
    }
    return ret;
}
```
## 3. 有重复，输入有序，找到所有坐标对
由于需要找到所有坐标对，直觉下第一反应是情况2的方法应该可以继续使用，需要改动的地方在于，当我们找到一组坐标后，不要停，继续查找。
在数据有序的情况下，相同元素总是紧邻。虽然两侧都可能出现相同元素，但其实两种情况的处理方式都是一样的，那么我们先假设左侧有相同元素出现。
比如输入数据为{0, 1, 1, 4, 6}，我们要查找的目标和为 7。
当p1 = 1, p2 = 4时，我们找到了一组位置，首先将这组位置加入结果，执行 ret.push_back(make_pair(p1, p2));
在执行 p1++，p2-- 开启下一轮查找之前，我们需要首先处理相等元素。这里我们使用一个栈来保存所有相同元素的坐标，而由于 p1 = 1 已经记录过，我们从 p1 = 2 开始，同时需要确保 p1 始终在 p2 之前
```c++
stack<int> stk;
while (nums[p1] == nums[p1 + 1] && p1 + 1 < p2) stk.push(++p1);
```
在将所有位置压栈之后，我们需要将元素再一个个pop出来，同时将p1，p2对放入结果数组。
```c++
while (!stk.empty()) {
    p1 = stk.top();
    ret.push_back(make_pair(p1, p2));
    stk.pop();
}
p1--;  // p1 恢复原位
```
由于我们是从 p1 = 2 开始压栈的，所以最后需要将 p1 恢复到原位置。

对右侧有相同元素的处理也是一样的
```c++
stack<int> stk;
    while (nums[p2] == nums[p2 - 1] && p2 - 1 > p1) stk.push(--p2);

    while (!stk.empty()) {
        p2 = stk.top();
        ret.push_back(make_pair(p1, p2));
        stk.pop();
    }
    p2++;  // 将p2归位
```
最后的完整代码如下：
```c++
vector<pair<int, int>> twoSum(vector<int>& nums, int target) {
  vector<pair<int, int>> ret;
  int p1 = 0, p2 = nums.size() - 1;

  while (p1 < p2) {
    if (nums[p1] + nums[p2] < target)
      p1++;

    else if (nums[p1] + nums[p2] > target)
      p2--;

    else {  // 找到坐标对
      ret.push_back(make_pair(p1, p2));
      if (p1 + 1 == p2) break;

      if (nums[p1] == nums[p1 + 1]) {  // 左侧有重复
        stack<int> stk;
        while (nums[p1] == nums[p1 + 1] && p1 + 1 < p2) stk.push(++p1);

        while (!stk.empty()) {
          p1 = stk.top();
          ret.push_back(make_pair(p1, p2));
          stk.pop();
        }
        p1--;  // p1 恢复原位
      }

      if (nums[p2] == nums[p2 - 1]) {  // 右侧有重复
        stack<int> stk;
        while (nums[p2] == nums[p2 - 1] && p2 - 1 > p1) stk.push(--p2);

        while (!stk.empty()) {
          p2 = stk.top();
          ret.push_back(make_pair(p1, p2));
          stk.pop();
        }
        p2++;  // p2 恢复原位
      }

      // 下一轮
      p1++;
      p2--;
    }
  }
  return ret;
}
```
当然了，不使用stack也是完全可以的，使用stack只是为了更好地说明运算过程。

## 4. 有重复，输入无序，找到所有坐标对
现在输入无序了，突然感觉是不是各种map又可以用了。但是仔细一看，输入有重复，而我们需要找到所有坐标对，这种情况下很明显，红黑树和哈希函数的map都无法处理。

同样是数据有重复，情况 3 就可以处理，和情况 4 唯一的区别在于情况 3 的输入数据是有序的。那么我们直接对输入排序，然后转成情况 3 可以吗？似乎可行。但是仔细一样，对输入排序不就把坐标信息破坏了。所以直接排序是不可行的。我们需要额外的方法记录元素与其坐标的关系。那么就很简单了，将输入元素值与其位置作为一个pair，放入vector<pair<int, int>> pairs，然后以元素值为关键字对pairs排序。这样我们就把情况 4 转换为了情况 3，唯一区别在于添加结果时添加的是 pair.second
```c++
vector<pair<int, int>> twoSum(vector<int>& nums, int target) {
  vector<pair<int, int>> ret;
  vector<pair<int, int>> pairs;

  for (int i = 0; i < nums.size(); ++i) {
    pairs.push_back(make_pair(nums[i], i));
  }
  sort(pairs.begin(), pairs.end());

  int p1 = 0, p2 = nums.size() - 1;

  while (p1 < p2) {
    if (pairs[p1].first + pairs[p2].first < target)
      p1++;
    else if (pairs[p1].first + pairs[p2].first > target)
      p2--;

    else {  // 找到坐标对
      ret.push_back(make_pair(pairs[p1].second, pairs[p2].second));
      if (p1 + 1 == p2) break;

      if (pairs[p1].first == pairs[p1 + 1].first) {  // 左侧有重复
        stack<int> stk;
        while (pairs[p1].first == pairs[p1 + 1].first && p1 + 1 < p2)
          stk.push(++p1);

        while (!stk.empty()) {
          p1 = stk.top();
          ret.push_back(make_pair(pairs[p1].second, pairs[p2].second));
          stk.pop();
        }
        p1--;  // p1 恢复原位
      }

      if (pairs[p2].first == pairs[p2 - 1].first) {  // 右侧有重复
        stack<int> stk;
        while (pairs[p2].first == pairs[p2 - 1].first && p2 - 1 > p1)
          stk.push(--p2);

        while (!stk.empty()) {
          p2 = stk.top();
          ret.push_back(make_pair(pairs[p1].second, pairs[p2].second));
          stk.pop();
        }
        p2++;  // 将p2归位
      }

      p1++;
      p2--;
    }
  }
  return ret;
}
```
## 总结
基于Hash和红黑树的map虽然查找效率很高，但是他们有个严重缺点就是难以处理相同元素。当有重复元素时，对输入进行排序，然后在有序输入中进行查找则通常来说会是一种有效的方法，比如二分查找。
