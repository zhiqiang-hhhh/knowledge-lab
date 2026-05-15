class Node:
    def __init__(self,val):
        self.val=val
        self.next=None
        
class MyLinkedList():

    def __init__(self):
        """
        Initialize your data structure here.
        """
        self.tail=self.head=None
        self.len=0
        
    def get(self, index):
        """
        Get the value of the index-th node in the linked list. If the index is invalid, return -1.
        :type index: int
        :rtype: int
        """
        if index<0 or index>=self.len:
            return -1
        if not self.head:
            return -1
        if index==self.len:
            return self.tail.val
        cur=self.head
        for pos in range(index):
            cur=cur.next    
        return cur.val

    def addAtHead(self, val):
        """
        Add a node of value val before the first element of the linked list. After the insertion, the new node will be the first node of the linked list.
        :type val: int
        :rtype: None
        """
        old=self.head
        self.head=Node(val)
        self.head.next=old
        
        if self._is_empty():
            self.tail=self.head
        
        self.len+=1       
        return None
        
    def addAtTail(self, val):
        """
        Append a node of value val to the last element of the linked list.
        :type val: int
        :rtype: None
        """
        if self._is_empty():
            self.tail=Node(val)
            self.head=self.tail
            self.len+=1
            return None
        self.tail.next=Node(val)
        self.tail=self.tail.next
        self.len+=1
        return None

    def addAtIndex(self, index, val):
        """
        Add a node of value val before the index-th node in the linked list. If index equals to the length of linked list, the node will be appended to the end of linked list. If index is greater than the length, the node will not be inserted.
        :type index: int
        :type val: int
        :rtype: None
        """
        if index<0 or index>self.len:
            return None
        if index==0 :
            self.addAtHead(val)
            return None

        cur=self.head
        for pos in range(index-1):
                cur=cur.next               
        n=Node(val)
        n.next=cur.next
        cur.next=n
        self.len+=1
        return None
    
    def deleteAtIndex(self, index):
        """
        Delete the index-th node in the linked list, if the index is valid.
        :type index: int
        :rtype: None
        """
        if index<0 or index>=self.len:
            return None
        if self._is_empty():
            return None
        if index==0:
            if self.len:
                self.head=self.next
                self.len-=1
            else:
                self.head=self.tail=None
            return None
        cur=self.head
        for pos in range(index-1):
            cur=cur.next    
        cur.next=cur.next.next
        self.len-=1
        return None
        
    def _is_empty(self):
        if self.len==0:
            return True
        return False

# Your MyLinkedList object will be instantiated and called as such:
# obj = MyLinkedList()
# param_1 = obj.get(index)
# obj.addAtHead(val)
# obj.addAtTail(val)
# obj.addAtIndex(index,val)
# obj.deleteAtIndex(index)
