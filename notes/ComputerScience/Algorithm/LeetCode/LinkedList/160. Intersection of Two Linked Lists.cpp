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