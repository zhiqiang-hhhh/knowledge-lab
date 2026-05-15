<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->
<!-- code_chunk_output -->

- [数组中的重复元素](#数组中的重复元素)
  - [有限值域](#有限值域)
    - [不允许修改数组](#不允许修改数组)
  - [包含重复元素且位置距离不超过 k](#包含重复元素且位置距离不超过-k)

<!-- /code_chunk_output -->

## 数组中的重复元素

### 有限值域
长度为 n 的数组，所有数字都在 0 到 n - 1 之间，找到任意一个重复元素。

解法是双循环，内层循环一直交换 nums[i] 与 nums[nums[i]]，直到 nums[i] == i。

复杂度分析：虽然有两重循环，但是实际上每个元素最多交换两次就可以回到它应该出现的 i 的位置，那么两重循环执行完最多只需要 2N 次交换。因此时间复杂度是 O(n)。
```cpp
class Solution {
public:
    bool containsDuplicate(vector<int>& nums) {
        size_t len = nums.size();

        for (size_t i = 0; i < len; ++i) {
            while (nums[i] != i) {
                if (nums[i] == nums[nums[i]]) {
                    return true;
                } else {
                    std::swap(nums[i], nums[nums[i]]);
                }
            }
        }
    }
};
```

#### 不允许修改数组
限制了数组元素的范围，因此如果没有重复，对于数组下标 i，数组元素中等于 i 的数量应该等于 1.
```cpp
class Solution {
public:
    bool containsDuplicate(vector<int>& nums) {
        size_t len = nums.size();
        size_t cnt = 0;
        for (size_t i = 0; i < len; i++) {
            cnt = 0;
            for (size_t j = 0; j < len; j++) {
                if (i == nums[j]) {
                    cnt++;
                }

                if (cnt > 1) {
                    return true;
                }
            }
        }

        return false;
    }
};
```
这个实现是 `O(n^2)` 的复杂度。考虑下 `O(nlog(n))`的解法。前面的解法里一次只检查一个位置，实际上可以多检查几个位置，判断条件也是类似的：对于区间 `[n,m]`，数组元素中属于 `[n,m]` 内的个数不应该超过 `m - n + 1`。增加检查位置之后实际上是减少了双重循环的外层循环的执行次数。

利用二分法每次检查一半的区间
```cpp
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
```

有点类似组合数学里的抽屉原理。

抽屉原理：有 N 双袜子要放到 n 个抽屉里，N > n，那么一定有抽屉里需要保存超过 1 双袜子。 

### 包含重复元素且位置距离不超过 k
[LeetCode 219](https://leetcode.com/problems/contains-duplicate-ii/description/)

朴素做法 1：
```cpp
class Solution {
public:
    bool containsNearbyDuplicate(vector<int>& nums, int k) {
        size_t len = nums.size();
        std::unordered_map<int, std::vector<size_t>> tbl;

        for (size_t i = 0; i < len; ++i) {
            if (tbl.contains(nums[i])) {
                std::vector<size_t>& v = tbl[nums[i]];
                v.push_back(i);
            } else {
                tbl[nums[i]] = std::vector<size_t>{i};
            }
        }

        for (auto& entry : tbl) {
            if (entry.second.size() < 2) {
                continue;
            }

            std::vector<size_t>& candidates = entry.second;
            std::sort(candidates.begin(), candidates.end());
            bool first = true;
            size_t prev = 0;

            for (auto itr = candidates.begin(); itr != candidates.end(); itr++) {
                if (first) {
                    first = false;
                    prev = *itr;
                    continue;
                }

                size_t dist = *itr - prev;
                if (dist <= k) {
                    return true;
                } else {
                    prev = *itr;
                }
            }
        }

        return false;
    }
};
```
朴素做法 2：
```cpp
class Solution {
public:
    bool containsNearbyDuplicate(vector<int>& nums, int k) {
        for (size_t i = 0; i < nums.size(); ++i) {
            for (size_t j = i + 1; j < nums.size() && j <= i + k; ++j) {
                if (nums[i] == nums[j]) {
                    return true;
                }
            }
        }

        return false;
    }
};
```
做法 2 的时间复杂读是 O(k*N) 的。

最优做法：滑动窗口。
```cpp
class Solution {
public:
    bool containsNearbyDuplicate(vector<int>& nums, int k) {
        std::unordered_set<int> win;
        size_t len = nums.size();

        for (size_t i = 0; i < len; ++i) {
            int cur = nums[i];
            if (win.contains(cur)) {
                return true;
            } else {
                win.insert(cur);

                if (win.size() > k) {
                    win.erase(nums[i-k]);
                }
            }
        }

        return false;

        return false;
    }
};
```