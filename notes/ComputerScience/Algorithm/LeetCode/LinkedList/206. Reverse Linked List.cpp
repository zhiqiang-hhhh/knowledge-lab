/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode(int x) : val(x), next(NULL) {}
 * };
 */
#include<iostream>
using namespace std;

struct ListNode {
      int val;
      ListNode *next;
      ListNode(int x) : val(x), next(NULL) {}
 };
class Solution {
public:
    ListNode* reverseList(ListNode* head) {
        ListNode *prev  = NULL;
        ListNode *cur   = head;
        while(cur != NULL){
            ListNode* temp = cur->next;
            cur->next = prev;
            prev = cur, cur = temp;
        }
         return prev;
    }
};