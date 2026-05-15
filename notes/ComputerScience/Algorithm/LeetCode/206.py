#Reverse Linked List
class ListNode:
    def __init__(self, x):
        self.val = x
        self.next = None
        

class Solution:
    def reverseList(self, head):
        cur, prev = head, None
        while cur:
            cur.next, prev, cur = prev, cur, cur.next
            #cur,prev,cur.next=cur.next,cur,prev
        return prev

    def reverseList_Recursion_S(self, head: 'ListNode') -> 'ListNode':
        'Single Recursion Function'
        if head:  #Not Empty
            next = head.next
            if next == None:  #One Element
                return head
            
            nnext = next.next
            
            if nnext == None:
                next.next = head
                head.next = None
                return next
            
            ans = self.reverseList_Recursion_S(next)
            
            next.next = head
            head.next = None

            return ans
        else:
            return []

    def reverseList_Recursion_D(self, head):
        return self._reverseList(head)

    def _reverseList(self, node, prev=None):
        if not node:
            return prev
        next = node.next
        node.next = prev
        return self._reverseList(next.node)


        
        
        