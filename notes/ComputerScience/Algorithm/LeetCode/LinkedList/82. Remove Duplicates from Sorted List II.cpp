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
    ListNode* deleteDuplicates(ListNode* head) {
        ListNode *dummy = new ListNode(0);
        dummy->next     =  head;
        
        ListNode *prev  = dummy;//last nonduplicate node
        ListNode *cur   = head;
        
        while(cur){
            int v = cur->val;
            if(cur->next != NULL && v == cur->next->val){
                cur = cur->next->next;
                while(cur != NULL &&  v == cur->val)
                    cur = cur->next;
                
                prev->next  = cur;  // 此时cur不一定为下一个 nonduplicate node，所以不移动 prev
            }
            else{
                prev = prev->next;
                cur = cur->next;
            }
        }
        
        head = dummy->next;
        return head;
    }
};