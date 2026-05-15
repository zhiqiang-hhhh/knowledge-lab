#include <iostream>
#include <string>
using namespace std;

class my {
 public:
  my() {}
  my(int item) { cout << "Constructor 2\n" << endl; }
};

int i5;

int main() {
  int i = 0;
  const int ci = i, &cr = ci;  // ci 是一个 const int，cr 也是一个 const int
  auto b = ci;                 // auto 会忽略顶层const，所以 b 为 int
  auto c = cr;                 // auto 会忽略顶层const，所以 c 为 int
  auto d = &i;                 // &i 为 int *，d 为 int *
  auto e = &ci;  // 对常量对象取地址得到底层const, 所以 &ci 为 const int*, e 为
                 // const int*, 指向整型常量的指针

  //底层const不是必须初始化。&ci 为底层const
  //顶层const必须初始化，初始值可以是非cosnt指针
  const int* pointer2const;
  int* const const_pointer = &i;

  int j = 10;
  int m = 11;

  pointer2const = &i;

  std::cout << const_pointer << std::endl;
  //  const_pointer = &j;
  std::cout << const_pointer << std::endl;

  std::cout << pointer2const << std::endl;
  pointer2const = &m;
  std::cout << pointer2const << std::endl;

  auto ri = ci * 2;
  auto pi = e;
  auto h = 42;
}