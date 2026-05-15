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
  ListNode* reverseBetween(ListNode* head, int m, int n) {
    if (head == NULL || m > n) return head;

    ListNode* dummy = new ListNode(0);
    dummy->next = head;

    // 将 prevM 移动到 M node 前一位
    ListNode* prevM = dummy;
    for (int i = 1; i < m; i++) {
      if (prevM != NULL) prevM = prevM->next;
    }
    if (prevM == NULL || prevM->next == NULL) {
      delete dummy;
      return head;
    }

    // 反转 M 到 N
    ListNode* prev = prevM->next;
    ListNode* cure = prev->next;

    for (int i = 0; i < n - m; i++) {
      if (cure != NULL) {
        auto temp = cure->next;
        cure->next = prev;
        prev = cure;
        cure = temp;
      } else {
        break;
      }
    }

    // 将反转之后的子链加进原链
    prevM->next->next = cure;
    prevM->next = prev;

    head = dummy->next;
    delete dummy;
    return head;
  }
};