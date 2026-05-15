#include <iostream>

void print(int (&arr)[10]) {
  for (auto elem : arr) std::cout << elem << ' ';
}

int main() {
  int array[10] = {12, 23, 34, 23, 45, 34, 65762, 27, 27};
  print(array);
}
