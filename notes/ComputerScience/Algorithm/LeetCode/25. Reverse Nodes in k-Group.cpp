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
        
        ListNode* pprev = dummy;
        ListNode* prev = dummy;
        ListNode* cure = head;
        
        while(cure != NULL){
            ListNode* guard = prev;
            for(int i = 0; i < k && guard != NULL; i++){
                guard = guard->next;
            }
            if(guard == NULL)
                break;
            
            for(int i = 0; i < k && cure != NULL; i++){   
               ListNode* temp = cure->next;
               cure->next = prev;
               prev = cure;
               cure = temp;
           }
            ListNode* temp = pprev->next;
            pprev->next = prev;
            pprev = temp;
            prev = pprev;
            prev->next = cure;
        }
        
        head = dummy->next;
        delete dummy;
        return head;
    }
};