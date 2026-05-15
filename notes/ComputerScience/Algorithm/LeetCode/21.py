# Merge Two Sorted Lists
# Definition for singly-linked list.
# class ListNode(object):
#     def __init__(self, x):
#         self.val = x
#         self.next = None

class Solution(object):
    def mergeTwoLists(self, l1, l2):
        """
        :type l1: ListNode
        :type l2: ListNode
        :rtype: ListNode
        """
        m1,m2=l1,l2
        if not m1:
            return m2
        if not m2:
            return m1
        '''
        if m1.val>=m2.val:
            tail=result=ListNode(m2.val)
            m2=m2.next
        else:
            tail=result=ListNode(m1.val)
            m1=m1.next
        '''
        tail=result=ListNode(None)
        while m1 and m2:          
            if m1.val>=m2.val:
                newNode=ListNode(m2.val)
                self.insertNode(tail,newNode)
                tail=newNode
                m2=m2.next
            else:
                newNode=ListNode(m1.val)
                self.insertNode(tail,newNode)
                tail=newNode
                m1=m1.next
        
        if m1:
            self.insertNode(tail,m1)
        if m2:
            self.insertNode(tail,m2)
        
        return result.next
            
        
    def insertNode(self,prev,node):
        prev.next=node