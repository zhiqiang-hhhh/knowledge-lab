class Solution(object):
    def maxSlidingWindow(self, nums, k):
        """
        :type nums: List[int]
        :type k: int
        :rtype: List[int]
        """
        if nums is None:
            return []
        #elemens in window represent the position in nums
        window,result=[],[]
        
        for i,key in enumerate(nums):
            
            #window is not empty, but full  
            if window and window[0]<=i-k:
                window.pop(0) 
                
            #window is not empty, some elements is smaller than key
            while(window and nums[window[-1]]<key):
                window.pop()
            
            window.append(i)
            if i>=k-1:
                result.append(nums[window[0]])
        
        return result 