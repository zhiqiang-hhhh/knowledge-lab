#include <array>
#include <iostream>

class my_elem {
 public:
  my_elem() { std::cout << "default constructor" << std::endl; }
  my_elem(const my_elem&) { std::cout << "copy constructor" << std::endl; }
  my_elem& operator=(const my_elem&) {
    std::cout << "assignment operator" << std::endl;
  }
  my_elem(const int&) { std::cout << "int constructor" << std::endl; }
};
