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