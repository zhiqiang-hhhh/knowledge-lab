#include <iostream>
#include <stdexcept>
#include <string>
#include <typeinfo>

int main(int argc, char* argv[]) {
  int i1, i2;
  // int t = 0;
  std::cout << "输入被除数和除数\n";
  while (std::cin >> i1 >> i2) {
    try {
      if (i2 == 0) throw std::invalid_argument("Second element can not be 0\n");
      std::cout << "Answer is :" << i1 / i2 << std::endl;

    } catch (std::invalid_argument err) {
      std::cout << err.what() << " Try again? y(default)/n \n";
      char res;
      std::cin >> res;
      if (res == 'n') break;
    }
  }
}