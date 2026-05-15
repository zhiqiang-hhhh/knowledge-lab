<!-- TOC -->

- [List](#list)
  - [Single List](#single-list)
      - [Remove Nth Node From End of List](#remove-nth-node-from-end-of-list)
      - [Swap Nodes in Pairs](#swap-nodes-in-pairs)
      - [Reverse Nodes in k-Group](#reverse-nodes-in-k-group)
  - [Two Lists](#two-lists)
      - [Merge Two Sorted Lists](#merge-two-sorted-lists)
      - [Intersection of Two Linked Lists](#intersection-of-two-linked-lists)
  - [Multiple Lists](#multiple-lists)
      - [Merge k Sorted Lists](#merge-k-sorted-lists)

<!-- /TOC -->
# List
链表的题目本身不难，它其实也是线性表的一种，算法来说和数组的算法基本相同。链表题目的难度在编程实现。当修改链表节点时，需要对节点的前继节点进行修改。比较重要的技巧包括使用dummyNode、双指针。

## Single List
#### Remove Nth Node From End of List
这道题的一个技巧在于先使用双指针，将tail指针向前移动 n - 1 个位置，然后再将两个指针同步向后移动，当tail指针到链表最后一个元素时，nthTailPrev就是需要删除节点的前继节点。
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
  ListNode* removeNthFromEnd(ListNode* head, int n) {
    ListNode *tail = head, *dummy = new ListNode(0);
    dummy->next = head;
    ListNode* nthTailPrev = dummy;

    for (int i = 1; i < n; ++i) {
      if (tail == nullptr) return head;
      tail = tail->next;
    }

    while (tail->next != nullptr) {
      tail = tail->next;
      nthTailPrev = nthTailPrev->next;
    }

    ListNode* nthTail = nthTailPrev->next;
    nthTailPrev->next = nthTail->next;
    delete nthTail;

    ListNode* ret = dummy->next;
    delete dummy;
    return ret;
  }
};
```
#### Reverse Linked List
反转链表，最基础的链表题目之一。
```cpp
/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode() : val(0), next(nullptr) {}
 *     ListNode(int x) : val(x), next(nullptr) {}
 *     ListNode(int x, ListNode *next) : val(x), next(next) {}
 * };
 */
class Solution {
public:
    ListNode* reverseList(ListNode* head) {
        if (head == nullptr || head->next == nullptr) {
            return head;
        }

        ListNode* tail = head;
        ListNode* before_tail = nullptr;

        while (tail != nullptr) {
            std::cout << tail->val << ' ';
            ListNode* after_tail = tail->next;
            tail->next = before_tail;
            before_tail = tail;
            tail = after_tail;
        }

        return before_tail;
    }
};
```
#### Swap Nodes in Pairs
成对地反转链表
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
  ListNode* swapPairs(ListNode* head) {
    ListNode* dummy = new ListNode(0);
    dummy->next = head;
    ListNode* tail = dummy;
    while (tail != nullptr) {
      tail = swapNodes(tail, tail->next);
    }

    ListNode* ret = dummy->next;
    delete dummy;
    return ret;
  }
  // 返回交换后靠后的节点
  ListNode* swapNodes(ListNode* prevN1, ListNode* prevN2) {
    if (prevN1 == nullptr || prevN2 == nullptr || prevN1->next == nullptr ||
        prevN2->next == nullptr)
      return nullptr;

    swap(prevN1->next, prevN2->next);
    swap(prevN1->next->next, prevN2->next->next);

    return prevN1->next->next;
  }
};
```
#### Reverse Nodes in k-Group
本题相当于Swap Nodes in Pairs的加强版，要求以k个Nodes为一组，进行reverse。

    Given this linked list: 1->2->3->4->5

    For k = 2, you should return: 2->1->4->3->5

    For k = 3, you should return: 3->2->1->4->5

思路和Swap Nodes in Pairs相同，需要一个子过程reverseKNodes，该过程将prevHead之后的k个节点reverse，返回reverse之后的最后一个节点。

比如输入为 1->2->3->4->5，k = 3，prevHead是 1 之前的dummy，执行reverseKNodes之后，输入变为 3->2->1->4->5，返回值为 ListNode pointer 指向 1 节点。

当prevHead之后的结点数量少于k时，无法进行reverse，返回nullptr。

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
  ListNode* reverseKGroup(ListNode* head, int k) {
    ListNode* dummy = new ListNode(0);
    dummy->next = head;

    ListNode* cur = dummy;
    while (cur != nullptr) cur = reverseKNodes(cur, k);

    ListNode* ret = dummy->next;
    delete dummy;
    return ret;
  }

  ListNode* reverseKNodes(ListNode* prevHead, int k) {
    ListNode* cur = prevHead;
    for (int i = 0; i < k; ++i) {
      cur = cur->next;
      if (cur == nullptr) return nullptr;
    }

    cur = prevHead;
    ListNode* tail = cur->next;

    for (int i = 0; i < k; ++i) {
      auto tmp = tail->next;
      tail->next = cur;
      cur = tail;
      tail = tmp;
    }

    swap(prevHead->next, cur);
    cur->next = tail;
    return cur;
  }
};
```
## Two Lists
#### Merge Two Sorted Lists
最为基础的双链表题目。
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
  ListNode* mergeTwoLists(ListNode* l1, ListNode* l2) {
    ListNode* dummy = new ListNode(0);
    ListNode* tail = dummy;

    while (l1 != nullptr && l2 != nullptr) {
      if (l1->val < l2->val) {
        tail->next = l1;
        l1 = l1->next;
      } else {
        tail->next = l2;
        l2 = l2->next;
      }
      tail = tail->next;
    }

    if (l1 != nullptr) tail->next = l1;
    if (l2 != nullptr) tail->next = l2;

    ListNode* ret = dummy->next;
    delete dummy;
    return ret;
  }
};
```
#### Intersection of Two Linked Lists
判断两条链表是否相交，两种方法：
1. 使用hashset来保存链表A中的所有节点，然后遍历链表B，判断当前节点是否在hashset中
2. 使用双指针。原理在于如果两条链表不相交，那么经过足够长的遍历次数后，两个指针一定会同时到达nullptr；否则在某个时刻一定有两个指针指向同一个节点。
   
```c++
class Solution {
 public:
  ListNode *getIntersectionNode(ListNode *headA, ListNode *headB) {
    ListNode *pA = headA, *pB = headB;
    if (pA == nullptr || pB == nullptr) return nullptr;

    while (pA != nullptr && pB != nullptr && pA != pB) {
      pA = pA->next;
      pB = pB->next;

      if (pA == pB) return pA;

      if (pA == nullptr) pA = headA;
      if (pB == nullptr) pB = headB;
    }
    return pA;
  }
};

class Solution {
 public:
  ListNode *getIntersectionNode(ListNode *headA, ListNode *headB) {
    unordered_set<ListNode *> nodeSet;

    while (headA != nullptr) {
      nodeSet.insert(headA);
      headA = headA->next;
    }

    while (headB != nullptr) {
      if (nodeSet.find(headB) != nodeSet.end()) return headB;
      headB = headB->next;
    }
    return nullptr;
  }
};
```
## Multiple Lists
#### Merge k Sorted Lists
这道题从直觉上来说感觉很简单，k个链表合并，先合并 list0 和list1，然后将合并结果和 list2 合并，然后重复上述过程直到结束。这个过程中，算法的时间复杂度是 `K*LOG(N)`

实现很简单，难点在于对合并过程的优化：上述过程虽然能够完成目标，但是当k非常大时，合并到最后会出现一个极长链表和一个极短链表合并的情况，这时mergeTwoLists过程很明显会做很多无用功：大量运算花在对极长链表的遍历上。


为了避免这种情况，比较好的方法是进行两两合并，将 k 条链表合并为 k / 2 条，再对 k / 2 条链表合并。尽量使得链表长度较为均匀。 这样算法的时间复杂度是 `Log(K)*Log(N)`

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
  ListNode* mergeKLists(vector<ListNode*>& lists) {
    if (lists.empty()) return nullptr;
    if (lists.size() == 1) return lists.front();

    int size = lists.size();

    while (size > 1) {
      cout << size;

      for (int i = 0; i < size / 2; ++i)
        lists[i] = mergeTwoLists(lists[i], lists[size - 1 - i]);

      size = (size + 1) / 2;
    }
    return lists.front();
  }

  ListNode* mergeTwoLists(ListNode* l1, ListNode* l2) {
    if (l1 == nullptr) return l2;
    if (l2 == nullptr) return l1;

    if (l1->val < l2->val) {
      l1->next = mergeTwoLists(l1->next, l2);
      return l1;
    } else {
      l2->next = mergeTwoLists(l1, l2->next);
      return l2;
    }
  }
};
```