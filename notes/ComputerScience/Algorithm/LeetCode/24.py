#Swap Nodes in Pairs
class ListNode:
    def __init__(self, x):
        self.val = x
        self.next = None

class Solution:
    def swapPairs(self, head):
        '''
        每次交换涉及到三个节点的next指针，prev,cur,paired
        每次交换之后只需要移动prev的位置，根据prev.next、prev.next.next来判断是否继续循环        
        '''
        prev = ListNode(None)
        prev.next = head
        
        if head and head.next:
            #至少有两个元素才进行交换,否则不必交换
            ans = head.next
        else:
            return head

        while prev.next and prev.next.next:
            cur, paired = prev.next, prev.next.next
            self._swap(prev, cur, paired)
            prev = cur
        
        return ans

            
    def _swap(self, prev, cur, paired):
        prev.next, cur.next, paired.next = paired, paired.next, cur
        
