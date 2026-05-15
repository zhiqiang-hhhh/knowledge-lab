#Linked List Cycle
# Definition for singly-linked list.

# class ListNode(object):
#     def __init__(self, x):
#         self.val = x
#         self.next = None

class Solution(object):
    def hasCycle(self, head):
        """
        :type head: ListNode
        :rtype: bool
        """
        '''
        使用快慢指针
        '''
        if  not head or not head.next:
            return False
        
        slower=faster=head
        
        while faster and faster.next:
            slower=slower.next
            faster=faster.next.next
            if slower is faster:
                return True
        return False