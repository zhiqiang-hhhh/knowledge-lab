import heapq

class KthLargest(object):

    def __init__(self, k, nums):
        """
        :type k: int
        :type nums: List[int]
        """
        self._k=k
        self._data=nums
        heapq.heapify(self._data)
        while(len(self._data)>k):
            heapq.heappop(self._data)
    
    def add(self, val):
        """
        :type val: int
        :rtype: int
        """
        if self._k>len(self._data):#is not full
                heapq.heappush(self._data,val)
                return self._data[0]
        #is full  
        if val>=self._data[0]:
                heapq.heappop(self._data)
                heapq.heappush(self._data,val)
                return self._data[0]
        else:
            return self._data[0]


# Your KthLargest object will be instantiated and called as such:
# obj = KthLargest(k, nums)
# param_1 = obj.add(val)