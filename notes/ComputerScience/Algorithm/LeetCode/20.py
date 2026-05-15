#Valid Parathese
class Solution(object):
    def __init__(self):
        self.data=Stack()
        self.charL=['(','[','{']
        self.charR=[')',']','}']
    def isValid(self, s):
        """
        :type s: str
        :rtype: bool
        """
        for cha in s:
            if cha in self.charL:
                self.data.push(cha)
                continue
            if cha in self.charR:
                ch=self.data.pop()
                if self.match(ch,cha):
                    continue
                else:
                    return False
        if self.data.is_empty():
            return True
        else:
            return False
            
    def match(self,a,b):
        if a==self.charL[0] and b==self.charR[0]:
            return True
        elif a==self.charL[1] and b==self.charR[1]:
            return True
        elif a==self.charL[2] and b==self.charR[2]:
            return True
        return False
        
class Stack():
    def __init__(self):
        self.data=[]
        self.size=0
    
    def push(self,val):
        self.data.append(val)
        self.size+=1
        
    def pop(self):
        if self.is_empty():
            return None
        else:
            ans=self.data.pop()
            self.size-=1
            return ans
    
    def is_empty(self):
        if self.size==0:
            return True
        return False
        