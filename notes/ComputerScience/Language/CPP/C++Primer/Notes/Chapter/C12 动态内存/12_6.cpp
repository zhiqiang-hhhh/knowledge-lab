#include <iostream>
#include <memory>
#include <vector>

std::vector<int>* vector_factory() { return new std::vector<int>; }

std::vector<int>* use_factory(std::vector<int>* pv) {
  int i;
  while (std::cin >> i) {
    pv->push_back(i);
  }
  return pv;
}

void print_vector(std::vector<int>* pv) {
  for (const auto obj : *pv) std::cout << obj << " ";
  std::cout << std::endl;
}

int main(int argc, char* argv[]) {
  std::vector<int>* pv = vector_factory();
  print_vector(use_factory(pv));
  delete pv;
}