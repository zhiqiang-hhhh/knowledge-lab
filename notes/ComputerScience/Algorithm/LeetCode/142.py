#Linked List Cycle II
# Definition for singly-linked list.
# class ListNode(object):
#     def __init__(self, x):
#         self.val = x
#         self.next = None

#A Video for Floyd's cycle detection algorithem :
#  https://www.youtube.com/watch?v=LUm2ABqAs1w

class Solution(object):
    def detectCycle1(self, head):
        """
        :type head: ListNode
        :rtype: ListNode
        最小内存使用
        """
        if not head or not head.next:
            return None
        
        collection=[head]
        
        cur=head.next
        while cur:
            if cur in collection:
                return cur
            collection.append(cur)
            cur=cur.next
        return None

    def detectCycle2(self, head):
        '''
        Floyd法
        '''
        has_cycle=False
        
        if not head or not head.next:
            return None
        
        slow=fast=head
        while fast and fast.next:
            slow=slow.next
            fast=fast.next.next
            if fast is slow:
                has_cycle=True
                break
                
        if has_cycle:
            slow=head
            while slow:
                if slow is fast:
                    return slow
                slow,fast=slow.next,fast.next
        else:            
            return None
                
