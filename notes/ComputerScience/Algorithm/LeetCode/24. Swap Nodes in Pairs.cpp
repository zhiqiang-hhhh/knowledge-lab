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
    ListNode* res = (head == NULL || head->next == NULL) ? head : head->next;

    ListNode* prev = dummy;
    ListNode* cure = head;

    while (cure != NULL) {
      cure = cure->next;

      if (cure != NULL) {
        ListNode* temp = cure->next;
        cure->next = prev->next;
        prev->next = cure;
        prev = cure->next;
        cure = temp;
        prev->next = cure;
      }
    }

    delete dummy;
    return res;
  }
};