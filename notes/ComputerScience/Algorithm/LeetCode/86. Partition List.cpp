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
  ListNode* partition(ListNode* head, int x) {
    ListNode* dummyLess = new ListNode(0);
    ListNode* dummyGrea = new ListNode(0);
    ListNode *less = dummyLess, *grea = dummyGrea;

    while (head != NULL) {
      if (head->val < x) {
        less->next = head;
        less = less->next;
      } else {
        grea->next = head;
        grea = grea->next;
      }
      head = head->next;
    }

    grea->next = NULL;
    less->next = dummyGrea->next;
    return dummyLess->next;
  }
};