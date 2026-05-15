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
// kSelect
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