#include <iostream>
#include <vector>
#include <algorithm>

class Solution {
public:
  // 抽屉原理方案：仅当值域大小 <= 元素数时，二分计数才能保证找到重复。
  // 否则值域过大，计数不会超载，需要回退到排序比较。
  bool containsDuplicate(std::vector<int> &nums) {
    size_t n = nums.size();
    if (n < 2) return false;

    int low = *std::min_element(nums.begin(), nums.end());
    int high = *std::max_element(nums.begin(), nums.end());
    long range_size = (long)high - (long)low + 1;

    if (range_size < (long)n) {
        return true;
    } else if (range_size == (long)n) {
      int left = low;
      int right = high;

      while (left < right) {
        long mid = ( (long)left + (long)right ) / 2;
        long cnt = 0;
        for (int v : nums) {
            if (v >= left && v <= mid) {
                cnt++;
            }
        }

        bool last_iteration = mid == left;
        long capacity = mid - left + 1;

        if (cnt > capacity) {
            if (last_iteration) {
                return true; // 找到重复, 值就是 left
            } else {
                right = (int)mid; // 重复在左区间
            }
        } else {
          left = (int)mid + 1; // 转向右区间
        }
      }
      return false;
    }

    // 回退：值域远大于元素个数，二分计数无法产生“超载”，用排序检查重复。
    std::vector<int> tmp = nums; // 保留原数据顺序
    std::sort(tmp.begin(), tmp.end());
    for (size_t i = 1; i < n; ++i) {
      if (tmp[i] == tmp[i-1]) return true;
    }
    return false;
  }
};

void test_case(std::vector<int> nums, bool expected) {
  std::cout << "Input: ";
  for (auto v : nums)
    std::cout << v << " ";

  std::cout << std::endl;

  Solution s;
  bool result = s.containsDuplicate(nums);

  std::cout << "Expected: " << expected << " | Got: " << result
            << (result == expected ? "  [OK]" : "  [FAIL]") << std::endl;
}

int main() {
  std::cout << "Testing containsDuplicate..." << std::endl;

  test_case({1, 2, 3, 4}, false);          // 没有重复
  test_case({1, 2, 3, 1}, true);           // 有重复
  test_case({5, 5, 5, 5}, true);           // 所有相同
  test_case({1}, false);                   // 单个元素
  test_case({1, 2}, false);                // 两个不同
  test_case({2, 1, 2}, true);              // 边界重复
  test_case({10, 20, 30, 40, 20}, true);   // 重复在中间
  test_case({1000000, -1, 1000000}, true); // 大数重复

  return 0;
}
