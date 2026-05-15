class Solution {
 public:
  static bool cmp(const vector<int>& v1, const vector<int>& v2) {
    return v1.front() < v2.front();
  }
  vector<vector<int>> merge(vector<vector<int>>& intervals) {
    return sortAndMerge(intervals);
  }

 private:
  void _merge(vector<int>& v1, vector<int>& v2) {
    v1.front() = min(v1.front(), v2.front());
    v1.back() = max(v1.back(), v2.back());
    v2.clear();
  }
  vector<vector<int>> sortAndMerge(vector<vector<int>>& intervals);
  vector<vector<int>> mapAndMerge(vector<vector<int>>& intervals);
};

vector<vector<int>> Solution::sortAndMerge(vector<vector<int>>& intervals) {
  if (intervals.size() <= 1) return intervals;

  sort(intervals.begin(), intervals.end(), cmp);

  vector<vector<int>> res{intervals[0]};
  size_t index = 1;

  while (index < intervals.size()) {
    vector<int>& interval = res.back();
    if (intervals[index].front() > interval.back()) {  // 新区间与旧区间不重合
      res.push_back(intervals[index++]);
    } else {
      interval.front() = min(interval.front(), intervals[index].front());
      interval.back() = max(interval.back(), intervals[index].back());
      index++;
    }
  }

  return res;
}

vector<vector<int>> Solution::mapAndMerge(vector<vector<int>>& intervals) {
  map<int, int> r2l;
  for (auto i : intervals) {
    int s = i.front(), e = i.back();
    auto it = r2l.lower_bound(s);

    while (it != r2l.end() && it->second <= e) {
      s = min(it->second, s);
      e = max(it->first, e);
      it = r2l.erase(it);
    }
    r2l[e] = s;
  }

  vector<vector<int>> res;
  for (const auto& i : r2l) {
    res.push_back(vector<int>{i.second, i.first});
  }
  return res;
}