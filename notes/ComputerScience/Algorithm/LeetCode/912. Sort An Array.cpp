class Solution {
 public:
  vector<int> sortArray(vector<int>& nums) {
    // return insertSort(nums);
    // mergeSort(nums, nums.begin(), nums.end());
    quickSort(nums, nums.begin(), nums.end());
    return nums;
  }

 private:
  vector<int>& insertSort(vector<int>&);
  void mergeSort(vector<int>&, vector<int>::iterator begin,
                 vector<int>::iterator end);
  // assume subsequences [nums[begin], nums[mid]), and [nums[mid], nums(end))
  // are both ascending order
  void merge(vector<int>&, vector<int>::iterator begin,
             vector<int>::iterator mid, vector<int>::iterator end);
  void quickSort(vector<int>& nums, vector<int>::iterator,
                 vector<int>::iterator);
  vector<int>::iterator partition(vector<int>& nums, vector<int>::iterator,
                                  vector<int>::iterator);
};

vector<int>& Solution::insertSort(vector<int>& nums) {
  if (nums.size() == 0 || nums.size() == 1) {
    return nums;
  }

  for (std::size_t xpos = 1; xpos != nums.size(); ++xpos) {
    const int key = nums.at(xpos);
    // std::cout << key << endl;
    int subpos = xpos - 1;

    while (subpos >= 0 && nums.at(subpos) >= key) {
      nums.at(subpos + 1) = nums.at(subpos);
      --subpos;
    }
    nums.at(subpos + 1) = key;
  }

  return nums;
}

void Solution::merge(vector<int>& nums, vector<int>::iterator begin,
                     vector<int>::iterator mid, vector<int>::iterator end) {
  auto temp = vector<int>();
  auto i1 = begin, i2 = mid;
  while (i1 != mid && i2 != end) {
    if (*i1 < *i2) {
      temp.push_back(*i1);
      i1++;
    } else {
      temp.push_back(*i2);
      i2++;
    }
  }

  if (i1 == mid)
    temp.insert(temp.end(), i2, end);
  else
    temp.insert(temp.end(), i1, mid);

  for (size_t i = 0; i < temp.size(); i++) {
    nums.at(begin - nums.begin() + i) = temp.at(i);
  }
}

void Solution::mergeSort(vector<int>& nums, vector<int>::iterator head,
                         vector<int>::iterator tail) {
  // tail 被视为尾后迭代器
  // tail - head <= 1 表示只有一个元素
  if (tail - head <= 1) return;

  // mid is an end iterator
  auto mid = head + (tail - head) / 2;

  mergeSort(nums, head, mid);
  mergeSort(nums, mid, tail);

  merge(nums, head, mid, tail);

  return;
}

void Solution::quickSort(vector<int>& nums, vector<int>::iterator begin,
                         vector<int>::iterator end) {
  if (end - begin <= 1) return;
  auto key_pos = partition(nums, begin, end);
  // cout << *(key_pos + 1) << endl;
  quickSort(nums, begin, key_pos);
  quickSort(nums, key_pos + 1, end);
}
vector<int>::iterator Solution::partition(vector<int>& nums,
                                          vector<int>::iterator begin,
                                          vector<int>::iterator end) {
  auto i = begin - 1;
  int key = *(end - 1);
  for (auto j = begin; j != end - 1; j++) {
    if (*j < key) {
      i += 1;
      swap(*j, *i);
    }
  }
  swap(*(i + 1), *(end - 1));
  return i + 1;
}
