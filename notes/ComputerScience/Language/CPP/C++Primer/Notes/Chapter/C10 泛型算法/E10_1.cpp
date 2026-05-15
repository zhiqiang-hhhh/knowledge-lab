#include <algorithm>
#include <iostream>
#include <vector>

int main() {
  std::vector<int> v;
  int e;
  int count = 0;
  while (std::cin >> e) {
    v.insert(v.end(), e);
    count++;
    if (count == 10) break;
  }
  std::cout << "输入目标值： " << std::endl;
  int t;
  std::cin >> t;
  std::cout << std::count(v.begin(), v.end(), t) << std::endl;
  ;
}