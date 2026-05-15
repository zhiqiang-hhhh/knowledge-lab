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
  ListNode* deleteDuplicates(ListNode* head) {
    // 几乎所有的链表题目都需要使用 dummy node
    ListNode* dummy = new ListNode(0);
    dummy->next = head;

    // prev vs cure
    ListNode* prev = dummy;
    ListNode* cure = head;

    while (cure != NULL) {
      // 取 val 之前一定要确保指针不为空
      while (cure->next != NULL && cure->val == cure->next->val) {
        // duplicate
        prev->next = cure->next;
        // C++ 需要注意对动态内存的释放
        delete cure;
        cure = prev->next;
      }
      // prev 与 cure 同时后移
      prev = cure;
      cure = cure->next;
    }
    head = dummy->next;
    delete dummy;
    return head;
  }
};