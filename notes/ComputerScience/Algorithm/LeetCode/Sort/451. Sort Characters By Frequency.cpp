// 桶排序
class Solution {
 public:
  string frequencySort(string s) {
    vector<list<char>> buckets(s.size() + 1);
    unordered_map<char, int> cnt;
    for (auto& c : s) {
      cnt[c]++;
    }

    for (auto& kv : cnt) {
      buckets[kv.second].push_back(kv.first);
    }

    string ret;
    for (int i = buckets.size() - 1; i >= 1; --i) {
      if (!buckets[i].empty()) {
        for (auto& c : buckets[i]) {
          // cout << c << ' ';
          ret.insert(ret.end(), i, c);
        }
      }
    }
    return ret;
  }
};

// 堆排序
class Solution {
 public:
  string frequencySort(string s) {
    unordered_map<char, int> cnt;
    for (auto& c : s) cnt[c]++;

    auto cmp = [](const pair<char, int>& p1, const pair<char, int>& p2) {
      return p1.second < p2.second;
    };

    priority_queue<pair<char, int>, vector<pair<char, int>>, decltype(cmp)> pq(
        cmp);

    for (auto& kv : cnt) {
      pq.push(kv);
    }

    string ret;
    while (!pq.empty()) {
      ret.insert(ret.end(), pq.top().second, pq.top().first);
      pq.pop();
    }
    return ret;
  }
};