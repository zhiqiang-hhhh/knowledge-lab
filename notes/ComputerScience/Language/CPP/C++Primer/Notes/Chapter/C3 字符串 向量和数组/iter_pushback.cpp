#include <iostream>
#include <string>
#include <vector>

bool func(std::vector<int>::iterator i1, std::vector<int>::iterator i2, int i) {
  while (i1 != i2) {
    if (*i1 == i) return true;
    i1++;
  }
  return false;
}

std::vector<int>::iterator func1(std::vector<int>::iterator begin,
                                 std::vector<int>::iterator end, int val) {
  while (begin != end) {
    if (*begin == val) return begin;
    begin++;
  }
  return end;
}

int main() {
  std::string s1;
  std::string::value_type item;
  std::vector<int> v1{1, 2, 3, 4, 454, 34324};
  std::vector<int>::reference i2 = *v1.begin();
  i2 = 12;
  for (const auto item : v1) {
    std::cout << item << " ";
  }
}