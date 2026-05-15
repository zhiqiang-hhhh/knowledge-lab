class Solution(object):
    def twoSum(self, nums, target):
        """
        :type nums: List[int]
        :type target: int
        :rtype: List[int]
        """
        if nums is None:
            return []
        
        nums_dict={}
        for i in range(len(nums)):
            if target-nums[i] not in nums_dict:
                nums_dict[nums[i]]=i
            else:
                return [nums_dict[target-nums[i]],i]
                
            
            