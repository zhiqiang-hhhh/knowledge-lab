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