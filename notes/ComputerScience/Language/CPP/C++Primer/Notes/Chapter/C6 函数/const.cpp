#include <iostream>

void func(const int* i) { std::cout << *i; }  // 底层 const
void func(int* const i) { std::cout << *i; }  // 顶层 const

// 形参的 const 不同，构成函数重载

int main() {
  // 顶层 const
  const int const_item = 0;
  int item;
  std::cin >> item;
  const int const_item2 = item;
  std::cout << const_item2 << std::endl;

  // 底层 const
  // 被底层 const 修饰的对象本身为非常量对象
  // pointer to const
  const int* ptc1;
  int const* ptc2;

  // 顶层 const
  // const pointer
  // 必须被初始化
  int* const cpi = &item;

  // 可以用一个常量对象去初始化一个非常量对象
  ptc1 = cpi;
  ptc2 = cpi;

  item = 2;
  std::cout << *cpi << ' ' << *ptc1 << std::endl;

  int i = 10;
  int& ir = i * 2;
}