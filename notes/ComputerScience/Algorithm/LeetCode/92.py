#Reverse Linked List II
# Definition for singly-linked list.
# class ListNode(object):
#     def __init__(self, x):
#         self.val = x
#         self.next = None

class Solution(object):
    def reverseBetween(self, head, m, n):
        """
        :type head: ListNode
        :type m: int
        :type n: int
        :rtype: ListNode
        """
        i=1
        dummy=ListNode(None)
        dummy.next=head
        
        while i<=m-1:
            dummy=dummy.next
            i+=1
        prev=dummy
        f=dummy=dummy.next
        i=m
        while i<n:
            dummy=dummy.next
            i+=1
        l=dummy
        tail=dummy.next
        l.next=None
        
        f,l=self.reverseList(f)
        prev.next=f
        l.next=tail
        
        if prev.val:
            return head
        else:
            return prev.next

    def reverseList(self,head):
        prev,curr=None,head
        while curr.next:
            curr.next,prev,curr=prev,curr,curr.next
        curr.next=prev
        return curr,head
        
        