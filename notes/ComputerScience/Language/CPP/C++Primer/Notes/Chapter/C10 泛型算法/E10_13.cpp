#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
// partition 将谓词为 true 的值排在容器前半部分
// 返回一个迭代器，指向最后一个使谓词为 true 的元素之后的位置

bool less_5(const std::string& s) { return s.size() < 5; }

int main() {
  std::vector<std::string> words{"fox", "jumps", "over", "quick",
                                 "res", "slow",  "the",  "turtle"};
  std::partition(words.begin(), words.end(), less_5);
  for (auto i : words) {
    std::cout << i << ' ';
  }

  std::vector<std::string> words2{"fox", "jumps", "over", "quick",
                                 "res", "slow",  "the",  "turtle"};
  int SZ = 4;
  std::partition(words2.begin(), words2.end(), [SZ](const std::string&s){return s.size() < SZ;});
  std::cout << "====\n";
  for (auto i : words2) {
    std::cout << i << ' ';
  }
}