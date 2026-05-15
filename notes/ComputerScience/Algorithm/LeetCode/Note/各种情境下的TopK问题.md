# TopK 问题
最基本的情景是所有数据放入内存，找出第K大的一个元素(1个)
进阶情景：数据全部放进内存，找出前K大的所有元素(K个)

继续进阶：输入的不是Key值，而是一个无序数组，要求找出其中出现频率最大的K个元素。
以上情景中，数据均可以放进内存，最终进阶：数据非常多50GB，内存只有100M，如何处理。
## 少量数据，可以全部读入内存
### 

### Top K Frequent Elements
输入无序数组nums，和 k。要求返回无序数组中出现频率最多的 k 个元素。

方法一：桶排序
```c++
// 桶排序
class Solution {
 public:
  vector<int> topKFrequent(vector<int>& nums, int k) {
    unordered_map<int, int> cnt;
    vector<int> ret;

    for (auto& num : nums) {
      cnt[num]++;
    }

    vector<list<int>> bucket(nums.size() + 1, list<int>());
    for (auto& kv : cnt) {
      bucket[kv.second].push_back(kv.first);
    }

    for (int i = bucket.size() - 1; i >= 0; --i) {
      while (!bucket[i].empty()) {
        ret.push_back(bucket[i].back());
        if (ret.size() >= k) return ret;
        bucket[i].pop_back();
      }
    }

    return ret;
  }
};
```
方法二：使用选择算法
`vector<pair<int, int>>`中，pair.first 为元素值，pair.second 为元素频数。使用 QuickSelect 算法，以 pair.second 为 key 对 vector 进行选择排序。
```c++
// quickSelectK
class Solution {
 public:
  vector<int> topKFrequent(vector<int>& nums, int k) {
    vector<pair<int, int>> freqArray;
    unordered_map<int, int> cnt;

    for (auto& num : nums) {
      cnt[num]++;
    }
    for (auto& kv : cnt) {
      freqArray.push_back({kv.second, kv.first});
    }

    vector<int> ret;
    auto pos = quickSelectK(freqArray, freqArray.begin(), freqArray.end(), k);
    while (pos < freqArray.end()) {
      ret.push_back(pos->second);
      pos++;
    }
    return ret;
  }

 private:
  vector<pair<int, int>>::iterator quickSelectK(
      vector<pair<int, int>>& nums, vector<pair<int, int>>::iterator begin,
      vector<pair<int, int>>::iterator end, int k) {
    auto key = begin->first;
    auto mid = begin;
    auto cur = mid;
    cur++;
    while (cur < end) {
      if (cur->first < key) {
        mid++;
        swap(*mid, *cur);
      }
      cur++;
    }
    swap(*mid, *begin);
    // cout << mid->first << ' ';

    if (end - mid == k) {
      return mid;
    } else if (end - mid > k) {
      return quickSelectK(nums, mid + 1, end, k);
    } else {
      return quickSelectK(nums, begin, mid, k - (end - mid));
    }
  }
};
```
方法三：使用堆排序。
利用小顶堆，输入保存`pair<int, int>`，pair.first 为频数，pair.second为元素值。
```c++
// 堆排序
class Solution {
 public:
  vector<int> topKFrequent(vector<int>& nums, int k) {
    unordered_map<int, int> cnt;
    for (auto& num : nums) {
      cnt[num]++;
    }

    priority_queue<pair<int, int>, vector<pair<int, int>>,
                   greater<pair<int, int>>>
        pq;
    for (auto& kv : cnt) {
      pq.push({kv.second, kv.first});
      if (pq.size() > k) pq.pop();
    }

    vector<int> ret;
    while (!pq.empty()) {
      ret.push_back(pq.top().second);
      pq.pop();
    }
    return ret;
  }
};
```
#### Top K Frequent Words
找出所有单词中出现次数最多的K个单词，对于出现频率相同的单词，结果中字典序较小的排在前。
```c++
// 桶排序
class Solution {
 public:
  vector<string> topKFrequent(vector<string>& words, int k) {
    vector<vector<string>> buckets(words.size());
    unordered_map<string, int> cnt;

    for (auto& word : words) {
      cnt[word]++;
    }

    for (auto& kv : cnt) {
      buckets[kv.second].push_back(kv.first);
    }

    vector<string> ret;
    for (int i = buckets.size() - 1; i >= 1; --i) {
      if (!buckets[i].empty()) {
        if (buckets[i].size() > 1) sort(buckets[i].begin(), buckets[i].end());
        for (const auto& word : buckets[i]) {
          ret.push_back(word);
          if (ret.size() == k) return ret;
        }
      }
    }
    return ret;
  }
};
```
```c++
// quickKSelect
class Solution {
 public:
  vector<string> topKFrequent(vector<string>& words, int k) {
    unordered_map<string, int> cnt;
    for (auto& word : words) {
      cnt[word]++;
    }

    vector<pair<string, int>> freqs;
    for (auto kv : cnt) {
      freqs.push_back({kv.first, kv.second});
    }

    vector<string> ret;
    int i = 1;
    while (i <= k) {
      auto kFreqItr = quickSelectK(freqs, freqs.begin(), freqs.end(), i);
      ret.push_back(kFreqItr->first);
      ++i;
    }
    return ret;
  }

 private:
  vector<pair<string, int>>::iterator quickSelectK(
      vector<pair<string, int>>& freq,
      vector<pair<string, int>>::iterator begin,
      vector<pair<string, int>>::iterator end, int k) {
    int key = begin->second;
    auto mid = begin, cur = mid;
    cur++;
    while (cur != end) {
      if (cur->second < key) {
        mid++;
        swap(*mid, *cur);
      } else if (cur->second == key && cur->first > begin->first) {
        mid++;
        swap(*mid, *cur);
      }
      cur++;
    }

    swap(*begin, *mid);
    if (end - mid > k)
      return quickSelectK(freq, mid + 1, end, k);
    else if (end - mid < k)
      return quickSelectK(freq, begin, mid, k - (end - mid));
    else
      return mid;
  }
};
```
```c++
// 堆排序
class Solution {
 public:
  vector<string> topKFrequent(vector<string>& words, int k) {
    unordered_map<string, int> cnt;
    for (auto& word : words) {
      cnt[word]++;
    }

    vector<pair<string, int>> freqs;
    for (auto kv : cnt) {
      freqs.push_back({kv.first, kv.second});
    }

    auto cmp = [](const pair<string, int>& p1, const pair<string, int>& p2) {
      return p1.second > p2.second ||
             ((p1.second == p2.second) && (p1.first < p2.first));
    };

    priority_queue<pair<string, int>, vector<pair<string, int>>, decltype(cmp)>
        pq(cmp);

    for (auto& kv : cnt) {
      pq.push(kv);
      if (pq.size() > k) pq.pop();
    }

    vector<string> ret;
    while (!pq.empty()) {
      ret.insert(ret.begin(), pq.top().first);
      pq.pop();
    }
    return ret;
  }
};
```

## 大量数据，无法全部读入内存
### 50 GB 数据，CPU 2 核，512 MB 内存
使用堆排序，内存中只需要常驻当前TopK，读取数据时只读取一个数据分组，比如 100 MB
### 50 GB 数据，CPU 2 核，2 GB 内存
1. 充分利用内存，读取数据时读取多个分组，比如 10 个；
2. 使用多线程在分组内部使用堆排序读取分组内的 TopK
3. 在10个TopK内使用QuickSelect得到本轮 TopK
4. 继续步骤 1

相比前一种方法，由于内存中数据变多，使用多线程查找TopK减少了总体运行时间。

## 超大量数据，多节点
### 100 TB 文件，200 节点
将100TB数据均分到 200 个结点上，节点内部使用多线程 + 组内堆排序 + QuickSelect 得到节点中数据的 TopK，然后将 200 个 TopK 全部放到一个节点，在单节点中查找最后的 TopK