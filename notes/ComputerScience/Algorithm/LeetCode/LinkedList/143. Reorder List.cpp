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
    /* data */
    int val;
    ListNode *next;
    ListNode(int x) : val(x), next(nullptr){}
};

class Solution {
public:
    void reorderList(ListNode* head) {
        if(head == NULL || head->next == NULL) return;
        
        ListNode *mid = findMid(head);
        ListNode *temp = mid->next;
        mid->next = NULL;
        mid = temp;
        
        ListNode *dummy1 = head;
        ListNode *dummy2 = reverseList(mid);
        
        head = mergeList(dummy1, dummy2);
        return;
    }
    
private:
    ListNode* findMid(ListNode* head){
        if(head == NULL || head->next == NULL) return head;
        ListNode* slow = head;
        ListNode* fast = head->next;
    
        while(fast != NULL && fast->next != NULL){
            slow = slow->next;
            fast = fast->next->next;
        }
        
        return slow;
    }
    
    ListNode* reverseList(ListNode* head){        
        ListNode* prev = NULL;
        ListNode* cur = head;
        
        while(cur != NULL){
            ListNode *temp = cur->next;
            cur->next = prev;
            prev = cur;
            cur = temp;
        }
        return prev;
    }
    
    ListNode* mergeList(ListNode* h1, ListNode* h2){
        ListNode* dummy = new ListNode(0);
        ListNode* tail = dummy;
        int i = 0;
        while(h1 != NULL && h2 != NULL){
            if(i % 2 == 0){
                tail->next = h1;
                h1 = h1->next;
            }
            else{
                tail->next = h2;
                h2 = h2->next;
            }
            tail = tail->next;
            i++; 
        }
        
        if(h1 != NULL)
            tail->next = h1;
        else
            tail->next = h2;
        
        return dummy->next;
    }
};