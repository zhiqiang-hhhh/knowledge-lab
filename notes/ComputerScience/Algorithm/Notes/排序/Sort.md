
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [主方法求解递归式](#主方法求解递归式)
- [比较排序](#比较排序)
  - [插入排序](#插入排序)
  - [归并排序(Merge Sort)](#归并排序merge-sort)
  - [堆排序](#堆排序)
    - [数组下标与孩子/父亲的计算](#数组下标与孩子父亲的计算)
    - [MAX-HEAPIFY(A, i)：把一个点“下沉”回到正确位置](#max-heapifya-i把一个点下沉回到正确位置)
    - [优先队列(Priority queues)](#优先队列priority-queues)
  - [快速排序](#快速排序)
    - [Partition 过程](#partition-过程)
    - [快排性能分析](#快排性能分析)
    - [三路快排](#三路快排)
  - [线性时间排序](#线性时间排序)
    - [计数排序](#计数排序)
    - [基数排序](#基数排序)
    - [桶排序](#桶排序)

<!-- /code_chunk_output -->


# 主方法求解递归式

常需要求解递归式来计算算法的运行时间。递归树方法不细说，较为直观。主方法提供一种菜谱式方法，熟悉之后使用起来最方便：

如果某个算法，将规模为 n 的问题分解为 a 个子问题，每个子问题规模为 n/b，其中 a 和 b 均为正常数。a 个子问题递归地求解，每个花费时间 T(n/b)，且将子问题分解与合并子问题花费的时间为函数 f(n)。则算法的运行时间可以描述为 T(n) = aT(n/b) + f(n)

1. 若对某个常数 ε > 0，有 $f(n)=O(n^{log_{b}a - \epsilon})$，则 $T(n)=O(n^{log_{b}a})$
2. 若 $f(n)=O(n^{log_{b}a})$，则 $T(n) = O(n^{log_{b}a}lgn)$
3. 若对某个常数 ε > 0，有 $f(n)=\Omega(n^{log_{b}a + \epsilon})$，且对某个常数c<1和所有足够大的 n 有 $af(n/b) \leq cf(n)$，则 $T(n) = O(f(n))$

简单理解，主定理的做法为：将函数 $f(n)$ 与 $n^{\log_{b}a}$ 进行大小比较，两个函数较大者决定了解的值。若 $n^{\log_{b}a}$ 较大，则解为$T(n)=O(n^{log_{b}a})$，若两者相当，则乘一个对数因子，解为$T(n) = O(n^{log_{b}a}lgn) = O(f(n)lgn)$，若 f(n) 较大，且满足某个条件(该条件在多项式界中多数满足)，则解为$O(f(n))$
# 比较排序
---
原地排序(Sorted in place)：在任何时刻，最多只有常数个数字是存储在数组之外的。
| 算法                    | 最坏运行时间       | 平均/期望运行时间  |
| ----------------------- | ------------------ | ------------------ |
| 插入排序                | $O(n^2)$      | $O(n^2)$      |
| 归并排序                | $O(n\log n)$  | $O(n\log n)$  |
| 堆排序                  | $O(n\log n)$       | ---                |
| 快速排序                | $O(n^2)$      | $O(n\log n)$  |
| 计数排序(Counting Sort) | $O(k + n)$    | $O(k + n)$    |
| 基数排序(Radix Sort)    | $O(d(n + k))$ | $O(d(n + k))$ |
| 桶排序(Bucket Sort)     | $O(n^2)$      | $O(n^2)$      |

插入排序，归并排序，堆排序，快速排序都是比较排序：通过比较元素大小来决定输入数组元素的位置。通过决策树模型可以证明比较排序的性能限制。通过该模型可以证明在规模为 n 的输入上，任何比较排序最差运行时间的下限为$\Omega(n\log n)$，这表明堆排序和归并排序具有渐进最优运行时间。

通过不比较元素的方法，可以突破$\Omega(n\log n)$的下界。比如计数排序。

## 插入排序
运行时间$O(n^2)$，原地排序。与打牌时整理手中的牌序相似。要求升序。
```
INSERTION-SORT(A)
    for j=2 to length[A]
        do key = A[j]
            // Insert A[j] in to sorted sequence A[1..j-1]
            i = j-1
            while i>0 and A[i]>key
                do A[i+1] = A[i]
                    i = i-1
            A[i+1] = key
```

`j` 标记第一个待排序元素的位置，`A[1...j-1]` 已经按照升序排好。插入排序最坏情况下的运行时间为$O(n^2)$，最好情况下运行时间为$O(n)$，且插入排序是一个原地排序。
```c++
class Solution {
public:
    vector<int> sortArray(vector<int>& nums) {
        int len = nums.size();
        for (int i = 0; i < len; ++i) {
            int cur = nums[i];

            for (int j = i - 1; j >= 0; --j) {
                if (nums[j] > cur) {
                    std::swap(nums[j], nums[j+1]);
                } else {
                    break;
                }
            }
        }
        return nums;
    }
};
```


## 归并排序(Merge Sort)
运行时间 $O(n\log n$)，非原地排序。

$T(n) = 2T(n/2) + n$

分治法思想：将问题分解为两个子问题，子问题除了问题规模小于原问题之外，其他都相同。因此算法可以多次递归掉调用其自身来解决相关的子问题。将子问题的解合并便得到原问题的解。
* 分解(Devide)
* 解决(Conquer)
* 合并(Combine)

归并排序：
* 分解：将 n 个元素分成各含 n/2 个元素的子序列
* 解决：用递归排序对两个子序列递归地排序
* 合并：合并两个已排序的子序列以得到排序结果

在数组和链表这两种数据结构上分别使用归并排序：

```c++
// Sort Array
class Solution {
public:
    vector<int> sortArray(vector<int>& nums) {
        mergeSort(nums, nums.begin(), nums.end());
        return nums;
    }
private:
    
    void mergeSort(vector<int>&, vector<int>::iterator begin,
                          vector<int>::iterator end);
    void merge(vector<int>&, vector<int>::iterator begin, 
                vector<int>::iterator mid, vector<int>::iterator end);
   
};
void Solution::merge(vector<int>& nums, vector<int>::iterator begin, 
                vector<int>::iterator mid, vector<int>::iterator end){
    auto temp = vector<int>();
    auto i1 = begin, i2 = mid;
    while(i1 != mid && i2 != end){
        if(*i1 < *i2){
            temp.push_back(*i1);
            i1++;
        }
        else{
            temp.push_back(*i2);
            i2++;
        }
    }
    
    if(i1 == mid) temp.insert(temp.end(), i2, end);
    else temp.insert(temp.end(), i1, mid);
    
    for(auto i = begin, j = temp.begin(); i != end; i++, j++)
            *i = *j;
}

void Solution::mergeSort(vector<int>& nums, vector<int>::iterator head, 
                                 vector<int>::iterator tail){
    // tail 被视为尾后迭代器
    // tail - head <= 1 表示只有一个元素
    if(tail - head <= 1) return;
    
    // mid is an end iterator
    auto mid = head + (tail - head) / 2;
    
    mergeSort(nums, head, mid);
    mergeSort(nums, mid, tail);
    
    merge(nums, head, mid, tail);
    
    return;
}
```
```c++
// Sort List
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
    ListNode* sortList(ListNode* head){
        return mergeSort(head);
    }
private:
    ListNode* mergeSort(ListNode*);
    ListNode* findMid(ListNode*);
    ListNode* merge(ListNode*, ListNode*);
};

ListNode* Solution::mergeSort(ListNode* head){
    if(head == NULL || head->next == NULL) return head;
    
    auto mid = findMid(head);
    auto left_list = head;
    auto right_list = mid->next;
    
    mid->next = NULL;
    
    left_list = mergeSort(left_list);
    right_list = mergeSort(right_list);
    
    return merge(left_list, right_list);
}

// 

ListNode* Solution::findMid(ListNode* head){
    if(head == NULL) return head;
    auto slow = head;
    // 若 fast 以 head 开始，则当 len=2 时返回的 mid 依然为第二个元素，导致 mergeSort 在 list 长度为 2 时无限循环
    auto fast = head->next;
    
    while(fast != NULL && fast->next != NULL){
        slow = slow->next;
        fast = fast->next->next;
    }
    
    return slow;
}

ListNode* Solution::merge(ListNode* l1, ListNode* l2){
    // 使用一个傀儡节点方便合并链表
    ListNode* dummy = new ListNode (0);
    ListNode* tail = dummy;
    
    while(l1 != NULL && l2 != NULL){
        if(l1->val <= l2->val){
            tail->next = l1;
            l1 = l1->next;
        }
        else{
            tail->next = l2;
            l2 = l2->next;
        }
        tail = tail->next;
    }
    
    if(l1 != NULL) 
        tail->next = l1;
    else
        tail->next = l2;
    
    ListNode* res = dummy->next;
    delete dummy;
    return res;
}

```
归并排序的运行时间在最好和最坏情况下都是$O(n\log{n})$，但是其 Merge 过程需要额外的空间。

## 堆排序
目标：把数组原地排序（升序），时间复杂度 $O(n\log n)$。

二叉堆（binary heap）可以用数组表示，并视为一棵完全二叉树。

二叉堆的性质：
1. **最大堆性质**：任意节点的值 $\ge$ 其左右孩子的值（所以堆顶是最大值）。
2. **heap-size**：当前“堆的有效长度”（排序过程中会逐渐缩小）。
3. 两个基本过程：`MAX-HEAPIFY`（修堆/下沉）和 `BUILD-MAX-HEAP`（建堆）。

### 数组下标与孩子/父亲的计算
下面的伪代码采用 CLRS 常用的 **1-based** 下标（A[1] 是堆顶）：

- PARENT(i) = $\lfloor i/2 \rfloor$
- LEFT(i) = $2i$
- RIGHT(i) = $2i + 1$

C++ 实现采用 **0-based** 下标（A[0] 是堆顶），因此宏是：

- parent(i) = $\lfloor (i-1)/2 \rfloor$
- left(i) = $2i + 1$
- right(i) = $2i + 2$

### MAX-HEAPIFY(A, i)：把一个点“下沉”回到正确位置
前提：以 `LEFT(i)`、`RIGHT(i)` 为根的两个子树都已经满足最大堆性质；但 `A[i]` 可能比孩子小。

做法：从 `i`、`left`、`right` 中选最大者，如果最大不是 `i`，就交换并递归/迭代到下一层。
```
MAX-HEAPIFY(A, i)
    l = LEFT(i)
    r = RIGHT(i)
    if l <= A.heap-size and A[l] > A[i]
        larger = l
    else
        larger = i
    if r <= A.heap-size and A[r] > A[larger]
        larger = r
    if larger != i
        exchange A[i] with A[larger]
        MAX-HEAPIFY(A, larger)
```
复杂度：最多向下走堆的高度 $h=\lfloor\log_2 n\rfloor$ 层，所以

$$T(\texttt{MAX-HEAPIFY}) = O(\log n)$$

**BUILD-MAX-HEAP(A)**
将一个数组`A[1...n]`转换为最大堆。

子数组$A[(\lfloor n/2\rfloor +1), n] $中的元素都是叶子节点。因此每个叶子节点本身就是一个最大堆，`BUILD-MAX-HEAP` build a max-heap in a bottom-up manner.

    BUILD-MAX-HEAP(A)
        A.heap-size = A.length
        for i = A.length/2 downto 1
            MAX-HEAPIFY(A, i)

这个过程“看起来”像调用了 $n/2$ 次 `MAX-HEAPIFY`，于是有人会误以为是 $O(n\log n)$。
但更准确的结论是：

$$T(\texttt{BUILD-MAX-HEAP}) = O(n)$$

直觉：靠近叶子的节点高度很小（下沉步数少），只有极少数节点高度接近 $\log n$，把所有节点的“可下沉层数”加起来是线性的。
```c++
#include <iostream>
#include <memory>
#include <string>
#include <vector>


#define parent(i) (i % 2) ? i >> 1 : (i >> 1) - 1
#define left(i) (i << 1) + 1
#define right(i) (i << 1) + 2

class heap {
 public:
  heap(size_t s);
  heap(std::initializer_list<int> il)
      : _spV(std::make_shared<std::vector<int>>(il)), heap_size(_spV->size()){ build_max_heap(_spV);};

  void print() {
    for (auto i : *_spV) std::cout << i << " ";
    std::cout << std::endl;
  }

 private:
  std::shared_ptr<std::vector<int>> _spV;
  size_t heap_size;
  void build_max_heap(std::shared_ptr<std::vector<int>>);
  void max_heapify(std::shared_ptr<std::vector<int>> A, size_t i);
};

// T(n) = O(n)
void heap::build_max_heap(std::shared_ptr<std::vector<int>> spV) {
  heap_size = spV->size();
  //
  size_t last_notLeaf = parent(heap_size);
  for (int i = last_notLeaf; i >= 0; i--) max_heapify(spV, i);
}

// T(n) = O(log n)
void heap::max_heapify(std::shared_ptr<std::vector<int>> spV, size_t i) {
  if (i >= heap_size) return;

  int rootval = spV->at(i);
  int li = left(i);
  int ri = right(i);
  size_t larger;
  if (li < heap_size && rootval < spV->at(li))
    larger = li;
  else
    larger = i;
  if (ri < heap_size && spV->at(larger) < spV->at(ri)) larger = ri;

  if (larger == i) return;
  int temp = spV->at(i);
  spV->at(i) = spV->at(larger);
  spV->at(larger) = temp;
  max_heapify(spV, larger);
}
```

**HEAPSORT**
有了最大堆后，排序就是反复“取最大值并缩堆”：

1. 交换堆顶（最大值）和堆尾 `A[n]`，这样最大值被放到了最终位置。
2. `heap-size -= 1`，把堆尾（已就位的最大值）从堆里移除。
3. 堆顶被换成了别的元素，可能破坏最大堆性质，对堆顶执行 `MAX-HEAPIFY` 重新修堆。

重复直到堆里只剩 1 个元素。

    HEAPSORT(A)
        BUILD-MAX-HEAP(A)
        for i = A.length downto 2
            exchange A[1] with A[i]
            A.heap-size -= 1
            MAX-HEAPIFY(A, 1)

HEAP操作中非常重要的一点就是利用好`heap-size`变量。
```c++

void heap::sort(){
  size_t largest = heap_size;
  // 边界条件是 i>0，只剩一个元素时不需要再排序
  for(size_t i = largest - 1; i > 0; i--){
    int temp = _spV->front();
    _spV->front() = _spV->at(i);
    _spV->at(i) = temp;
    heap_size--;
    max_heapify(_spV, 0);
  }
  heap_size = _spV->size();
}
```

### 优先队列(Priority queues)
堆排序很好，但是快速排序在实际中性能更好(更小的时间常数)。堆排序常用来实现优先队列。

**Priority Queue**
优先队列是一种用来保存 S 个元素的数据结构，每个元素具有一个 key 值。一个最大优先队列(max-priority queue)支持以下操作：
* INSERT(S, x) 将元素 x 插入集合 S
* MAXIMUM(S) 返回具有最大值 key 的元素
* EXTRACT-MAX(S) removes and returns the element of S with the largest key.
* INCEREASE-KEY(S, x, k) increses the value of element x's key to the new value k, k 必须大于等于 x 的当前 key 值。

使用堆来实现一个优先队列。优先队列中的元素对应具体应用中的一个对象。常常需要确定优先队列中元素和应用对象的对应关系。因此需要在 heap element 中保存对应于应用对象的 handle。headle 的具体实现取决于应用。比如，array index。

**HEAP-MAXIMUM(A)**
    return A[1]

**HEAP-EXTRACT-MAX(A)**

    HEAP-EXTRACT-MAX(A)
        if A.heap-size < 1
            error"heap underflow"
        max = A[1]
        A[l] = A[A.heap-size]
        A.heap-size -= 1
        MAX-HEAPIFY(A, 1)
        return max



## 快速排序
原地排序，最坏运行时间为$O(n^2)$，平均运行时间为$O(n\log(n))$，实际中常常优于堆排序。因为其平均性能非常好($O(n lgn)$，且隐含的常数因子非常小)，所以通常是用于排序的最佳实用选择。

插入排序、归并排序、堆排序和快速排序都是比较排序：通过对数组中的元素进行比较来实现排序。

快速排序也是基于分治法思想。
* 分解(Devide)：数组`A[p..r]`被分解成为子数组`A[p...q-1]`和`A[q+1...r]`，使得`A[p...q-1]`中的每个元素都小于或等于`A[q]`且小于等于`A[q+1...r]`中的元素。下标 q 也在划分过程中重新计算。
* 解决(Conquer)：对两个子数组继续采用快速排序
* 合并(Combine)：因为两个数组都是原地排序，所以合并不需要其他操作，数组已经排序好。
  
```
QuickSort(A, p, r)
    if p < r
        q = partition(A, p, r)
        QuickSort(A, p, q-1)
        QuickSort(A, q+1, r)
```
### Partition 过程
```c++
partition(A, p, r)
    x = A[r]    // A[r] 为关键字
    i = p-1 // i 是左子数组的最右侧位置，左子数组中的元素小于等于 key
            // i + 1 标识右子数组的第一个位置，右子数组的元素大于等于 key
    // j 标识待排序的元素位置
    for j=p to r-1
        do if A[j] <= x
            then i = i + 1 // i = i + 1 后，i 为第一个大于等于 key 元素的位置               
            exchange(A[i], A[j])// exchange 后，i 位置的元素变成了小于等于 key 的“最后”一个元素 
    //  将 key 值复位
    exchange(A[i+1], A[r])
    return i+1
```
Partition 过程采用技巧，来实现将数组 A 重排，重拍之后，子数组`A[p...q-1]`中的元素都小于等于`A[q]`小于等于`A[q+1...r]`。返回`q`。

很明显，partition 过程的运行时间为$O(n)$

### 快排性能分析
快排的运行时间和`partition`过程划分的子数组是否对称有关，而是否对称又与选择哪个元素作为关键字有关。

**最坏情况划分**
当 n 个元素被划分为 n-1 个元素和 1 个关键字以及一个包含 0 个元素的子数组时，快排的运行时间达到$O(n^2)$。T(n) = T(n-1) + O(n)

也就是说，当数组本身就是已经排好序的数组时，会出现最坏情况。

**平均运行时间**
快排的平均运行时间非常接近于最佳运行时间。因为在哪怕 9：1 的划分下也是最佳运行时间。事实上，**任何一种常数比例的划分都会产生深度为Θ(lg n)的递归树，因此只要划分是常数比例的，那么运行时间总是O(n lgn)**

```c++
// Sort Array
void Solution::quickSort(vector<int>&nums, vector<int>::iterator begin, vector<int>::iterator end){
    if(end - begin <= 1 ) return;
    auto key_pos = partition(nums, begin, end);
    //cout << *(key_pos + 1) << endl;
    quickSort(nums, begin, key_pos);
    quickSort(nums, key_pos + 1, end);
}

vector<int>::iterator Solution::partition(vector<int>&nums, vector<int>::iterator begin, vector<int>::iterator end){
    auto i = begin - 1;
    int key = *(end - 1);
    for(auto j = begin; j != end - 1; j++){
        if(*j < key){
            i += 1;
            swap(*j, *i);
        }
    }
    swap(*(i + 1), *(end - 1));
    return i + 1;
}
```
LeetCode 148，Sort List
```c++
// Sort List
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
    ListNode* sortList(ListNode* head){
       return quickSort(head);
       //return mergeSort(head);
    }
private:
    ListNode* quickSort(ListNode* head);
    ListNode* partition(ListNode* head);
    ListNode* mergeSort(ListNode*);
    ListNode* findMid(ListNode*);
    ListNode* merge(ListNode*, ListNode*);
};

ListNode* Solution::quickSort(ListNode* head){
    if(head == NULL || head->next == NULL) return head;
    
    // 以第一个元素作为 key 值进行 partition
    auto l_head = partition(head);
    auto g_head = head->next;
    head->next = NULL;
    
    l_head = quickSort(l_head);
    g_head = quickSort(g_head);

    head->next = g_head;
    return l_head;
}

ListNode* Solution::partition(ListNode* head){
    if(head == NULL || head->next == NULL) return head;
    
    auto key = head->val;
        
    auto l_dummy = new ListNode(0), g_dummy = new ListNode(0);
    auto l_tail = l_dummy, g_tail = g_dummy;
        
    while(head != NULL){
        if(head->val < key){
            l_tail->next = head;
            l_tail = l_tail->next;
        }
        else{
            g_tail->next = head;
            g_tail = g_tail->next;
        }
        head = head->next;
    }
    
    g_tail->next = NULL;
    l_tail->next = g_dummy->next;
    
    delete g_dummy;
    
    auto res = l_dummy->next;
    delete l_dummy;
    return res;
}
```
### 三路快排
最基础的快排使用固定位置的元素作为 pivot 进行 partition 的参照物，这种算法对于有序/倒序数组的时间复杂度为 O(n^2)，改进方法是使用 random 的 pivot。
random 的 pivot 对于全相等数组依然是 O(n^2) 的时间复杂度，解决办法是使用三路 partition：把数组切分为 
* < pivot
* = pivot
* `>` pivot

的三个区间。
```cpp
void quickSort(vector<int>& nums, int l, int r) {
    if (l >= r) return;

    // +1 确保存在将最后一个元素选为 pivot 的可能
    int pivot = nums[l + rand() % (r - l + 1)];
    // lt, gt 把区间分为三个分段，小于，等于，大于
    int lt = l, i = l, gt = r;

    // 
    while (i <= gt) {
        if (nums[i] < pivot)
            swap(nums[lt++], nums[i++]);
        else if (nums[i] > pivot)
            swap(nums[i], nums[gt--]);
        else
            i++;
    }

    quickSort(nums, l, lt - 1);
    quickSort(nums, gt + 1, r);
}
```

## 线性时间排序
**对于包含 n 个元素的输入序列来说，任何比较排序在最坏情况下都要经过Ω(n lgn)次比较**。通过决策树模型证明。

### 计数排序

计数排序假设 n 个输入的每一个元素都是位于 0 到 k 之间的一个整数。

基本思想：对于每个 x，统计输入中小于 x 的数的个数，然后把 x 直接放到输出数组对应的位置即可。

### 基数排序

### 桶排序