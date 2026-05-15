/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode(int x) : val(x), next(NULL) {}
 * };
 */
#include<iostream>
struct ListNode
{
    int val;
    ListNode *next;
    ListNode(int x) : val(x), next(NULL){}
};

class Solution {
public:
    ListNode* reverseBetween(ListNode* head, int m, int n) {
        if(head == NULL || head->next == NULL || m >= n) return head;
        
        ListNode* dummy = new ListNode(0);
        dummy->next = head;
        
        ListNode* prev = dummy;
        //Move prev to m-1 node
        for(int i = 0; i < m - 1 && prev != NULL; i++)
            prev = prev->next;
        
        //cur is first m node
        ListNode* cur = prev->next;
        ListNode* realp = prev;
        ListNode* realt = prev->next;
        
        //reverse m to n node
        for(int i = 0; i <= n - m && cur != NULL; i++){
            ListNode* temp = cur->next;
            cur->next = prev;
            
            prev = cur;
            cur = temp;            
        }
        
        realp->next = prev;
        realt->next = cur;
        
        return  dummy->next;       
    } 
};