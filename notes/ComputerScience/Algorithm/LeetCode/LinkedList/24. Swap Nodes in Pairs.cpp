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
  ListNode* swapNodes(ListNode* prevN1, ListNode* prevN2) {
    if (prevN1 == nullptr || prevN2 == nullptr || prevN1->next == nullptr ||
        prevN2->next == nullptr)
      return nullptr;

    swap(prevN1->next, prevN2->next);
    swap(prevN1->next->next, prevN2->next->next);

    return prevN1->next->next;
  }
};