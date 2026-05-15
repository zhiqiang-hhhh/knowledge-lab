#Implement Queue using Stack
class MyQueue(object):

    def __init__(self):
        """
        Initialize your data structure here.
        """
        self.stackL=[]
        self.stackR=[]
        self.size=0
        self.front=None
        
    def push(self, x):
        """
        Push element x to the back of queue.
        :type x: int
        :rtype: None
        """
        if self.stackL:
            self.stackL.append(x)
        else:
            for y in list(self.stackR):
                elem=self.stackR.pop()
                self.stackL.append(elem)
            self.stackL.append(x)
        self.front=self.stackL[0]
        return None 
    
    def pop(self):
        """
        Removes the element from in front of queue and returns that element.
        :rtype: int
        """
        if self.stackR:
            ans=self.stackR.pop()
            if self.stackR:
                self.front=self.stackR[0]
            else:
                self.front=None
        
        else:
            for y in list(self.stackL):
                elem=self.stackL.pop()
                self.stackR.append(elem)
            ans=self.stackR.pop()
        if self.stackR:
            self.front=self.stackR[-1]
        return ans
    
    def peek(self):
        """
        Get the front element.
        :rtype: int
        """
        return self.front

    def empty(self):
        """
        Returns whether the queue is empty.
        :rtype: bool
        """
        if not self.stackL and not self.stackR:
            return True
        return False       


# Your MyQueue object will be instantiated and called as such:
# obj = MyQueue()
# obj.push(x)
# param_2 = obj.pop()
# param_3 = obj.peek()
# param_4 = obj.empty()