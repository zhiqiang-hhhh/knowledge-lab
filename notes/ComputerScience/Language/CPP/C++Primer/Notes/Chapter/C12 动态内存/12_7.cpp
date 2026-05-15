#include <iostream>
#include <memory>
#include <vector>

std::shared_ptr<std::vector<int>> vector_factory() {
  return std::make_shared<std::vector<int>>();
}

std::shared_ptr<std::vector<int>> use_factory(
    std::shared_ptr<std::vector<int>> pv) {
  int i;
  while (std::cin >> i) {
    pv->push_back(i);
  }
  return pv;
}

void print_vector(std::shared_ptr<std::vector<int>> pv) {
  for (const auto obj : *pv) std::cout << obj << " ";
  std::cout << std::endl;
}

int main(int argc, char* argv[]) {
  std::shared_ptr<std::vector<int>> pv = vector_factory();
  print_vector(use_factory(pv));
}