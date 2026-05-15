#include <array>
#include <deque>
#include <forward_list>
#include <iostream>
#include <list>
#include <vector>

class my_elem {
 public:
  my_elem() { std::cout << "default constructor" << std::endl; }
  my_elem(const my_elem&) { std::cout << "copy constructor" << std::endl; }
  my_elem& operator=(const my_elem&) {
    std::cout << "assignment operator" << std::endl;
  }
  my_elem(const int&) { std::cout << "int constructor" << std::endl; }
};

int main() {
  std::list<my_elem> my_list;
  my_elem item;

  std::cout << "1=====" << std::endl;
  my_list.push_front(item);
  my_list.emplace_front();

  std::cout << "2=====" << std::endl;
  my_elem item1(item);
  my_list.push_back(item1);
  my_list.emplace_back(item1);

  std::cout << "3=====" << std::endl;
  my_elem item2(2);
  my_list.emplace(my_list.cend(), item2);
  my_list.emplace(my_list.cend(), 2);

  std::string str;
  std::vector<std::string> svec;
  std::deque<std::string> sq;
  std::forward_list<std::string> sf;
  std::list<std::string> sl;
  std::string word;
  std::cin >> word;
  const size_t size = 100;
  std::array<std::string, size> sarr;
}
