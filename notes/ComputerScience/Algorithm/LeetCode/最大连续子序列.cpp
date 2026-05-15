/*
最大子序列：输入序列中，总和最大的连续子序列
关键点：总和最大+连续

输入规则：
 第一行表示输入数据的个数
 第二行为真实输入
 输入数据个数为 0 表示结束程序

输出规则：
 对每个测试用例，在1行里输出最大和、最大连续子序列的第一个和最后一个元素，中间用空格分隔。
 如果最大连续子序列不唯一，则输出序号i和j最小的那个（如输入样例的第2、3组）。
 若所有K个元素都是负数，则定义其最大和为0，输出整个序列的首尾元素。

输入样例：
6
-2 11 -4 13 -5 -2
10
-10 1 2 3 4 -5 -23 3 7 -21
6
5 -8 3 2 5 0
1
10
3
-1 -5 -2
3
-1 0 -2
0

输出样例：
20 11 13
10 1 4
10 3 5
10 10 10
0 -1 -2
0 0 0
*/

#include <iostream>
#include <memory>
#include <vector>

std::shared_ptr<std::vector<int>> input(std::istream& in) {
  size_t s;
  in >> s;
  if (s == 0)
    return std::make_shared<std::vector<int>>();
  else {
    auto v_sptr = std::make_shared<std::vector<int>>(s);
    auto i = v_sptr->begin();
    while (in >> *(i++)) {
      if (i == v_sptr->end()) break;
    }
    return v_sptr;
  }
}

struct memo_elem {
  int sum = 0;
  int first;
  int last;
};

memo_elem dp_BCS(std::shared_ptr<std::vector<int>> vp) {
  std::vector<int> res;
  std::vector<memo_elem> memo;
  for (const auto& i : *vp) {
    if(memo.size() != 0 && memo.back().sum >= 0 ){
      memo_elem temp;
      temp.sum = i + memo.back().sum;
      temp.last = i;
      temp.first = memo.back().first;
      memo.push_back(temp);
    }
    else{
      memo_elem temp;
      temp.sum = i;
      temp.first = i;
      temp.last = i;
      memo.push_back(temp);
    }

  }
  auto b = memo.begin();
  for (auto i = memo.begin(); i < memo.end(); i++) {
    if (i->sum > b->sum) b = i;
  }
  if(b->sum < 0){
    memo.back().sum = 0;
    memo.back().first = memo.front().first;
    return memo.back();
  }
  else{
    return *b;
  }
}

int main() {
  while (true) {
    auto vp = input(std::cin);
    if (vp->size() == 0) {
      break;
    }
    auto ans = dp_BCS(vp);
    std::cout << ans.sum << ' ' << ans.first << ' ' << ans.last << std::endl;
  }
  return 0;
}