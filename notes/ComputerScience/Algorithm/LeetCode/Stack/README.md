<!-- TOC -->

- [Stack](#stack)
  - [Stack and String](#stack-and-string)
      - [Mini Parse](#mini-parse)
      - [Flatten Nested List Iterator](#flatten-nested-list-iterator)
      - [Evaluate Reverse Polish Notation](#evaluate-reverse-polish-notation)
  - [Stack and Array](#stack-and-array)
      - [Trapping Rain Water](#trapping-rain-water)
      - [Largest Rectangle in Histogram](#largest-rectangle-in-histogram)
      - [Maximal Rectangle](#maximal-rectangle)
      - [总结](#%e6%80%bb%e7%bb%93)

<!-- /TOC -->
# Stack
## Stack and String
#### Mini Parse
这道题和我在面试阿里云时遇到的算法题很相似。本题是解析嵌套的整数，当时的题是解析嵌套的HashMap

懒得说题目细节了，直接把LeetCode原文抄过来。

Given a nested list of integers represented as a string, implement a parser to deserialize it.

Each element is either an integer, or a list -- whose elements may also be integers or other lists.

Note: You may assume that the string is well-formed:

String is non-empty.
String does not contain white spaces.
String contains only digits 0-9, [, - ,, ].
    
    Example 1:

    Given s = "324",

    You should return a NestedInteger object which contains a single integer 324.
    Example 2:

    Given s = "[123,[456,[789]]]",

    Return a NestedInteger object containing a nested list with 2 elements:

    1. An integer containing value 123.
    2. A nested list containing two elements:
        i.  An integer containing value 456.
        ii. A nested list with one element:
            a. An integer containing value 789.

这道题两个做法，一个是递归，另一个非递归。很明显了，使用非递归的话肯定会用到栈。

算法方面其实没啥好说的，就是递归思想的实际使用。
> 非递归使用栈

以一个输入为例：输入为`[123,[456,[789]],211,985]`
那么我们最后得到的NestedInteger应该包含三个整数，分别为123,211和985，同时还有一个子NestedInteger，该对象内有一个整数456，和一个孙子NestedInteger，孙子NestedInteger内包含一个整数为789。

分析这个输入：
1. 只要我们遇到一个`[`，就说明我们开始遇到一个NestedInteger
2. 如果遇到一个`,`，说明此处可能是数字的中断，也可能是NestedInteger的中断，但是有一点可以确认：`,`之后一定是新“过程”的开始
3. 如果遇到一个`]`，说明这是一个NestedInteger的结束

首先使用stack非递归来做。很明显，stack中保存的元素应该为NestedInteger，以上述输入为例，stack中元素从栈底到栈顶元素应该依次为：`[123,211,985],[456],[789]`。栈中靠下的元素应该包含之上的元素。
所以我们很明显会需要一个过程：
```
NestedInteger ni;
while(!stk.empty()){
    ni = stk.top();
    stk.pop();
    stk.top().add(ni);
}
```
这样的到的最后的ni就是结果。
但是我们会发现，我们很难按照上述方式构造栈！因为当我们遇到第二个`[`时，需要把123压栈，当我们遇到第三个`[`时，需要把456压栈，而当我们遇到211时，211实际上是最外层Integer的元素，而此时该Integer已经被压入栈底。

所以这给了我们一个提示，即我们需要用栈顶元素来保存当前应该插入的NestedInteger。比如：当我们遇到123时，栈顶元素应为一个`[]`，当我们遇到456时，栈顶元素应该为`[]`，当我们遇到789时，栈顶元素应该为`[456]`，当我们遇到211时，栈顶元素应该为`[123,[456,[789]]]`

集合之前的输入分析，可以得出：
1. 遇到一个`[`时，我们需要往栈中压入一个空NestedInteger
2. 当遇到一个`,`时，我们需要往栈顶元素中add一个整数
3. 当遇到`]`时，说明一个NestedInteger结束，需要将该NestedInteger添加到它的父NestedInteger中，实现如下：
```c++
NestedInteger ni = stk.top();
if(!stk.empty())
    stk.top().add(ni);
else
    stk.push(ni);
```
最终代码实现如下：
```c++
/**
 * // This is the interface that allows for creating nested lists.
 * // You should not implement it, or speculate about its implementation
 * class NestedInteger {
 *   public:
 *     // Constructor initializes an empty nested list.
 *     NestedInteger();
 *
 *     // Constructor initializes a single integer.
 *     NestedInteger(int value);
 *
 *     // Return true if this NestedInteger holds a single integer, rather than
 * a nested list. bool isInteger() const;
 *
 *     // Return the single integer that this NestedInteger holds, if it holds a
 * single integer
 *     // The result is undefined if this NestedInteger holds a nested list
 *     int getInteger() const;
 *
 *     // Set this NestedInteger to hold a single integer.
 *     void setInteger(int value);
 *
 *     // Set this NestedInteger to hold a nested list and adds a nested integer
 * to it. void add(const NestedInteger &ni);
 *
 *     // Return the nested list that this NestedInteger holds, if it holds a
 * nested list
 *     // The result is undefined if this NestedInteger holds a single integer
 *     const vector<NestedInteger> &getList() const;
 * };
 */
class Solution {
 public:
  NestedInteger deserialize(string s) {
    stack<NestedInteger> stk;
    auto isDigit = [](const char& c) { return (c == '-') || isdigit(c); };

    if (isDigit(s.front())) {
      return stoi(string(s.begin(), s.end()));
    }

    auto itr = s.begin();
    while (itr < s.end()) {
      if (isDigit(*itr)) {
        auto valueEnd = find_if_not(itr, s.end(), isDigit);
        if (stk.empty())  // 用于处理输入为单个整数的情况，这种情况下没有[]
          stk.push(NestedInteger(stoi(string(itr, valueEnd))));
        else
          stk.top().add(stoi(string(itr, valueEnd)));

        itr = valueEnd;
      } else {
        if (*itr == '[') {
          stk.push(NestedInteger());
        } else if (*itr == ']') {
          NestedInteger ni = stk.top();
          stk.pop();
          if (stk.empty())  // 用于处理输入为[]的情况
            stk.push(ni);
          else
            stk.top().add(ni);
        }
        ++itr;
      }
    }
    return stk.top();
  }
};
```
> 递归

本题实际上解析只有两个对象，一个是对以`[`开头的NestedInteger解析，另一个是对数字的解析。解析NestedInteger时需要用到对数字的解析。实现如下：
```c++
class Solution {
  NestedInteger parse(string& s, int& pos) {
    if (s[pos] == '[') return parseNestedList(s, pos);
    return parseInteger(s, pos);
  }

  NestedInteger parseInteger(string& s, int& pos) {
    int sign = s[pos] == '-' ? -1 : 1;
    if (s[pos] == '+' || s[pos] == '-') ++pos;
    int num = 0;
    while (isdigit(s[pos])) {
      num = num * 10 + s[pos++] - '0';
    }
    num *= sign;
    return NestedInteger(num);
  }

  NestedInteger parseNestedList(string& s, int& pos) {
    NestedInteger ni;
    // pos++;
    while (s[pos] != ']') {
      pos++;  // skip , and first [
      if (s[pos] == ']') break;
      ni.add(parse(s, pos));
    }
    pos++;
    return ni;
  }

 public:
  NestedInteger deserialize(string s) {
    int pos = 0;
    return parse(s, pos);
  }
};
```

#### Flatten Nested List Iterator
本题要求对一个嵌套的 Integer List 进行 flatten。

Given a nested list of integers, implement an iterator to flatten it.

Each element is either an integer, or a list -- whose elements may also be integers or other lists.

    Example 1:

    Input: [[1,1],2,[1,1]]
    Output: [1,1,2,1,1]
    Explanation: By calling next repeatedly until hasNext returns false, 
                the order of elements returned by next should be: [1,1,2,1,1].
    Example 2:

    Input: [1,[4,[6]]]
    Output: [1,4,6]
    Explanation: By calling next repeatedly until hasNext returns false, 
                the order of elements returned by next should be: [1,4,6].

需要实现三个函数，NestedInteger构造函数，hasNext()用来判断是否还有可供打印的整数，next()则返回一个可供打印的整数，同时将迭代器向后移动一位。

以输入
`[123,456,[789,211],985]`
`[345]`
`[398,[921,347]]`
为例来进行分析

题目提供了NestedInteger对象的三个接口
* bool isInteger() const; 判断当前NestedInteger是否为sigle integer
* int getInteger() const; 如果只有single integer则返回该值
* const vector<NestedInteger> &getList() const; 将NestedInteger中的元素以一个vector的形式返回

从提供的接口来看，唯一可以获得NestedInteger中整数的情况是：NestedInteger(之后简称NI)中只有single integer。所以我们需要把嵌套结构的NI进行flatten，将它分解为一个个包含single integer的NI。

下面的代码展示了采用递归如何对一个NestedInteget进行flatten
```c++
void flatten(const NestedInteger& nestedInteger){
  if(nestedInteger.isInteger()){
    cout << nestedInteger.getInteger() << ' ';
    return;
  }
  vector<NestedInteger>& vNI = nestedList.getList();
  for(auto& ni : vNI){
      flatten(ni);
  }
  return;
}
```
如果使用栈+非递归：
```c++
void flatten(const NestedInteger& nestedInteger){
  stack<NestedInteger> stk;
  if(nestedInteger.isInteger())
    cout << nestedInteger.getInteger();

  vector<NestedInteger>& vNI = nestedList.getList();
  for(auto rItr = vNI.rbegin(); rIte < vNI.rend(); ++rItr)
    stk.push(*rItr);

  while(!stk.empty()){
    if(stk.top().isInteger()){
      cout << stk.top().getInteger() << ' ';
      stk.pop();
    }

    vector<NestedInteger>& vNI = nestedList.getList();
    for(auto rItr = vNI.rbegin(); rIte < vNI.rend(); ++rItr)
      stk.push(*rItr);
  }

  return;
}
```
OK，我们现在知道如何处理一个NestedInteger的情况了。那么应该如何处理`vector<NestedInteger>`呢？

显而易见：对`vector<NestedInteger>`中的每个NI单独进行flatten即可。

```c++
void flattenVectorNI(const vector<NestedInteger>& nestedList){
  for(auto& ni : nestedList)
    flatten(ni);
}
```
回到本题！额额额额额，本题要求是实现NestedIterator，而不是简单地直接flatten。

当然了，如果想直接套用之前的代码也是可以的，暴力flatten，把所有输出保存在queue中，NestedIterator一次遍历一个输出即可。这种实现好处在于NestedIterator.next()和NestedIterator.hasNext()的效率会很高。缺点在于NestedIterator构造函数的运行时间会很长(暴力flatten肯定是要在构造函数中进行的)，而且没有做到“按需”遍历。

为了做到按需，我们需要一个栈。每次调用hasNext时，我们对栈顶的NI进行flatten，这是一个迭代的过程，当栈顶NI中只包含single integer时，返回true。栈顶之下的NI保持不动，当迭代器遍历到它时再进行flatten。如果stk为空，说明所有的NI已经遍历过了，返回false
```c++
bool hasNext() {
    while (!stk.empty()) {
      if (stk.top()->isInteger()) return true;

      // stk.top() is not a single Integer
      // maybe another NestedInteger，or a []
      // need flatten
      auto& vNI = stk.top()->getList();
      stk.pop();
      if (vNI.empty())  // precess []
        continue;

      for (auto i = vNI.end() - 1; i >= vNI.begin(); --i) stk.push(i);
    }
    return false;
  }
```

对于next函数，它只会在hasNext返回为true时才会调用，所以直接返回`stk.top().getInteget()`即可，返回之前需要将栈顶元素pop。
```c++
  int next() {
    int ret = stk.top()->getInteger();
    stk.pop();
    return ret;
  }
```
为了提高效率，我在栈中保存了迭代器而不是NI本身。完整代码如下：

```c++
/**
 * // This is the interface that allows for creating nested lists.
 * // You should not implement it, or speculate about its implementation
 * class NestedInteger {
 *   public:
 *     // Return true if this NestedInteger holds a single integer, rather than
 * a nested list. 
 *      bool isInteger() const;
 *
 *     // Return the single integer that this NestedInteger holds, if it holds a
 * single integer
 *     // The result is undefined if this NestedInteger holds a nested list
 *     int getInteger() const;
 *
 *     // Return the nested list that this NestedInteger holds, if it holds a
 * nested list
 *     // The result is undefined if this NestedInteger holds a single integer
 *     const vector<NestedInteger> &getList() const;
 * };
 */

class NestedIterator {
 public:
  NestedIterator(vector<NestedInteger>& nestedList) {
    if (nestedList.empty())  // process []
      return;

    for (auto i = nestedList.end() - 1; i >= nestedList.begin(); --i)
      stk.push(i);
  }

  int next() {
    int ret = stk.top()->getInteger();
    stk.pop();
    return ret;
  }

  bool hasNext() {
    while (!stk.empty()) {
      if (stk.top()->isInteger()) return true;

      // stk.top() is not a single Integer
      // maybe another NestedInteger，or a []
      // need flatten
      auto& vNI = stk.top()->getList();
      stk.pop();
      if (vNI.empty())  // precess []
        continue;

      for (auto i = vNI.end() - 1; i >= vNI.begin(); --i) stk.push(i);
    }
    return false;
  }

 private:
  stack<vector<NestedInteger>::iterator> stk;
};

/**
 * Your NestedIterator object will be instantiated and called as such:
 * NestedIterator i(nestedList);
 * while (i.hasNext()) cout << i.next();
 */
```
#### Evaluate Reverse Polish Notation
计算一个逆波兰表达式。
方式：递归和使用栈的非递归。


## Stack and Array
#### Trapping Rain Water
这道题有两种做法，一种是基于Stack，另一种基于数组双指针。这里记录基于Stack的方法。

想象下雨的过程，雨水肯定是先淹没沟槽的最深区间。当最深区间被淹没以后，次最深区间就成了最深区间。我们用一个Stack来保存降序的深度。那么Stack.top就是当前未被淹没的最深位置，Stack.top的下面的一个元素就是次最深区间。


最深区间的面积取决于两个点：
1. 左右沟的最低高度
2. 左右沟的间隔

在Stack和数组结合情况中，一个技巧是使用Stack保存数组的坐标而不是直接保存数组的值。

```c++
int botPos = stk.top();
  stk.pop();
  if(!stk.empty()){
      int validHeight = min(height[cur], height[stk.top()]);
      ret += (validHeight - height[botPos]) * (cur - stk.top() - 1);
```
上述代码计算了最深区间Water的面积，`stk.pop`将已经被淹没的区间排除

在计算过最深区间之后，cur代表的右沟可能还需要和次最深区间计算面积，也可能cur变为新的最深，所以cur不动，重新开始循环。

下面是完整代码
```c++
class Solution {
public:
    int trap(vector<int>& height) {
        if(height.size() <= 2)
            return 0;
        
        stack<int> stk; // stk 为一个单调递减栈
        int ret = 0;
        int cur = 0;
        while(cur < height.size()){
            if(stk.empty() || height[cur] <= height[stk.top()])
                stk.push(cur++);  // 遇到新 bot
            else{
                // stk.top() 保存的是 bot 的位置
                int botPos = stk.top();
                // 当最底层装过水以后，最底层已经不再是最底层，所以需要pop
                stk.pop();
                if(!stk.empty()){
                    // 此时stk.top()保存可用的最低左边挡板位置
                    int validHeight = min(height[cur], height[stk.top()]);
                    // 添加新增水域面积
                    // 这里的新增水域面积是以最低左边挡板计算的
                    ret += (validHeight - height[botPos]) * (cur - stk.top() - 1);
                }
                // 由于左边挡板有可能有多个
                // 所以cur不能移动
                // cur可能还需要和次最低左边挡板计算面积执行第15行
                // 或者cur成为新bot，执行第12行
            }
        }
        return ret;
    }
};
```

#### Largest Rectangle in Histogram
这道题和 Trapping Rain Water 思路基本一致。

很明显，柱状图中矩形的面积与其中包含的最低bar相关。对于每个bar X，我们假设 X 为它周围bar中的最低高度，然后求以在这个假设情况下的局部矩形的面积。怎么求呢，我们需要知道X左侧第一个小于X的bar的位置，以及X右侧第一个小于X的bar的位置。

比如，一段bar的高度为`254673`，如果要求以4作为最低bar的矩形的面积，那么面积应该为`4 * width，width = 4`，width是`2~3`之间bar的个数。

We need to know index of the first smaller (smaller than ‘x’) bar on left of ‘x’ and index of first smaller bar on right of ‘x’. Let us call these indexes as ‘left index’ and ‘right index’ respectively.

当我们遍历过所有bar，计算过每个bar对应上述矩形的面积之后，就可以得到全局的最大矩形面积。

计算对应矩形的面积，最重要的是找到 left index 和 right index。

朴素的做法那就是遍历，这种做法整体时间复杂度为O(n*n)。

巧妙的做法：

我们要找的是距离当前X最近的小于X的index，单调栈可以帮我们。
```c++
class Solution {
 public:
  int largestRectangleArea(vector<int>& heights) {
    if (heights.empty()) return 0;

    stack<int> stk; // 单调递增栈
    int curPos = 0;
    int maxArea = INT_MIN;

    while (curPos < heights.size()) {
      if (stk.empty() || heights[curPos] >= heights[stk.top()])
        stk.push(curPos++);
        
      else {
        // curHeight > stk.top
        // 如果我们以heights[stk.top]作为最低bar
        // 那么 curPos 就是 right index
        // stk.top 下的第一个元素就是 left index
        int botPos = stk.top();
        stk.pop();

        int leftPos = stk.empty() ? -1 : stk.top();
        int tmpArea = heights[botPos] * (curPos - leftPos - 1);
        maxArea = max(maxArea, tmpArea);
      }
    }

    // 处理未被处理过的bar
    // 极端情况下如果 bar 单调递增，那么前面的while循环中一次面积都不计算
    while (!stk.empty()) {
      int botPos = stk.top();
      stk.pop();

      int leftPos = stk.empty() ? -1 : stk.top();
      int tmpArea = heights[botPos] * (curPos - leftPos - 1);
      maxArea = max(maxArea, tmpArea);
    }
    return maxArea;
  }
};
```
#### Maximal Rectangle
本题输入为一个矩阵，矩阵元素只有1和0。要求找到1构成的矩形的最大面积。

    Input:
    [
      ["1","0","1","0","0"],
      ["1","0","1","1","1"],
      ["1","1","1","1","1"],
      ["1","0","0","1","0"]
    ]
    Output: 6

方法：矩阵转为“直方图”，然后按照Largest Rectangle in Histogram的方法计算以每行为底的最大矩形面积。

比如，对于上述输入矩阵，我们可以得到如下直方图矩阵

    4 0 3 0 0 
    3 0 2 3 2 
    2 1 1 2 1 
    1 0 0 1 0 

然后按行计算Largest Rectangle in Histogram，得到最后的结果。
```c++
class Solution {
 public:
  int maximalRectangle(vector<vector<char>>& matrix) {
    if (matrix.size() == 0) return 0;

    int maxArea = 0;

    int rowSize = matrix.size();
    int colSize = matrix[0].size();
    vector<vector<int>> histograms(rowSize, vector<int>(colSize, 0));

    for (int row = 0; row < rowSize; ++row) {
      // 计算每一行的直方图
      for (int col = 0; col < colSize; ++col) {
        int i = row, j = col;
        while (i < rowSize && matrix[i][j] == '1') {
          histograms[row][col] += 1;
          i++;
        }
      }

      maxArea = max(maxArea, reactangleHistogram(histograms[row]));
    }
    return maxArea;
  }

 private:
  int reactangleHistogram(const vector<int>& histogram) {
    stack<int> stk;
    int i = 0, maxArea = 0;

    while (i <= histogram.size()) {
      int curHeight = (i == hisgotram.size()) ? -1 : histogram[i];

      if (stk.empty() || curHeight > histogram[stk.top()]) {
        stk.push(i++);
        continue;
      }

      int height = histogram[stk.top()];
      stk.pop();
      int leftIndex = stk.empty() ? -1 : stk.top();
      int rightIndex = i;
      maxArea = max(maxArea, height * (rightIndex - leftIndex - 1));
    }
    return maxArea;
  }
};
```
#### 总结
栈不光是一种先进后出，可以反应先后顺序的结构，我们也可以将其用作“排序”，尤其是当我们需要寻找类似“最近的大于/小于当前值”的元素时，单调栈可以派上用场。单调栈的详细笔记见`Node/Monotone Stack`

栈和数组结合时，栈内保存index要比单纯保存value要好。该技巧在栈与便于进行查找的数据结构（HashMap，红黑树等）结合时也可以使用。

