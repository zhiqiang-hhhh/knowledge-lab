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