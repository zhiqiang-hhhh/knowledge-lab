class Solution {
 public:
  vector<vector<int>> insert(vector<vector<int>>& intervals,
                             vector<int>& newInterval) {
    return _insert(intervals, newInterval);
  }

 private:
  // 24 ms 13.4 MB
  vector<vector<int>> _mapInsert(vector<vector<int>>& intervals,
                                 vector<int>& newInterval);
  // 8 ms 12.4 MB
  vector<vector<int>> _insert(vector<vector<int>>& intervals,
                              vector<int>& newInterval);
};

vector<vector<int>> Solution::_mapInsert(vector<vector<int>>& intervals,
                                         vector<int>& newInterval) {
  map<int, int> r2l;
  intervals.push_back(newInterval);
  for (auto& i : intervals) {
    auto it = r2l.lower_bound(i.front());
    while (it != r2l.end() && it->second <= i.back()) {
      i.front() = min(it->second, i.front());
      i.back() = max(it->first, i.back());
      it = r2l.erase(it);
    }
    r2l[i.back()] = i.front();
  }

  vector<vector<int>> res;
  for (auto i : r2l) {
    res.push_back(vector<int>{i.second, i.first});
  }
  return res;
}

vector<vector<int>> Solution::_insert(vector<vector<int>>& intervals,
                                      vector<int>& newInterval) {
  size_t index = 0;
  vector<vector<int>> res;
  while (index < intervals.size() &&
         intervals[index].back() < newInterval.front()) {
    res.push_back(intervals[index++]);
  }

  while (index < intervals.size() &&
         intervals[index].front() <= newInterval.back()) {
    newInterval.front() = min(newInterval.front(), intervals[index].front());
    newInterval.back() = max(newInterval.back(), intervals[index].back());
    index++;
  }
  res.push_back(newInterval);
  while (index < intervals.size()) {
    res.push_back(intervals[index++]);
  }

  return res;
}