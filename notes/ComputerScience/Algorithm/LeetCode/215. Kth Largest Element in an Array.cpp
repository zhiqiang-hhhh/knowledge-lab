#include <iostream>
#include <queue>
#include <vector>
using namespace std;

class Solution {
 public:
  int findKthLargest(vector<int>& nums, int k) {
    return quickSortK(nums, nums.begin(), nums.end(), k);
  }

 private:
  int heapSort(vector<int>&, const int);
  int quickSortK(vector<int>&, vector<int>::iterator, vector<int>::iterator,
                 const int k);
  vector<int>::iterator partition(vector<int>&, vector<int>::iterator,
                                  vector<int>::iterator);
  void exchange(vector<int>::iterator, vector<int>::iterator);
};

int Solution::heapSort(vector<int>& nums, const int k) {}

int Solution::quickSortK(vector<int>& nums, vector<int>::iterator begin,
                         vector<int>::iterator end, const int k) {
  if (end - begin <= 1) return *begin;
  auto mid = partition(nums, begin, end);

  // 通过判断 mid 的位置与 k 的关系，将运行时间降低为O(nlogk)
  if (nums.end() - mid == k)
    return *mid;
  else if (nums.end() - mid < k)
    return quickSortK(nums, begin, mid, k - (nums.end() - mid));

  else
    return quickSortK(nums, mid + 1, end, k);
}

vector<int>::iterator Solution::partition(vector<int>& nums,
                                          vector<int>::iterator begin,
                                          vector<int>::iterator end) {
  if (end - begin <= 1) return begin;

  int key = *begin;
  auto less = begin, ori = begin;
  begin += 1;
  while (begin != end) {
    if (*begin < key) {
      exchange(++less, begin);
    }
    begin++;
  }
  exchange(ori, less);
  return less;
}

void Solution::exchange(vector<int>::iterator i1, vector<int>::iterator i2) {
  int temp = *i1;
  *i1 = *i2;
  *i2 = temp;
}
