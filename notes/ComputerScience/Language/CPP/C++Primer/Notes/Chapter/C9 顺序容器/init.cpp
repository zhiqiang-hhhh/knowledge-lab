#include <array>
#include <deque>
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
  /*
std::vector<int> v1;  // v1 为空
std::cout << v1.size() << std::endl;
std::vector<int> v2(v1);  // v2 为空
// 等价方式：std::vector<int> v2 = v1;
std::vector<int> v3 = v2;      // v3 为空
std::vector<int> v4{1, 2, 3};  // 列表初始化为 1，2，3
// 等价方式：std::vector<int> v5 = {1, 2, 3};  // 列表初始化为 1，2，3
std::vector<int> v6(v4.cbegin(),
                    v4.cend());  // 迭代器传范围参数，v6 中元素为 1，2，3
std::vector<int> v7(10);  // 10个元素，均值初始化为 0
for (const auto i : v7) std::cout << i << ' ';
std::cout << std::endl;

std::vector<int> v8(10, 1);  // 10 个 1
for (const auto i : v8) std::cout << i << ' ';
std::cout << std::endl;
*/
  std::cout << "1.0 =====" << std::endl;
  std::vector<my_elem> v1;

  std::cout << "2=====" << std::endl;
  std::vector<my_elem> v2(v1);

  std::cout << "3=====" << std::endl;
  std::vector<my_elem> v3 = v2;

  std::cout << "4=====" << std::endl;
  std::vector<my_elem> v4{1, 2, 3};
  std::vector<my_elem> t0(v4);
  std::vector<my_elem> t1 = v4;

  std::cout << "5=====" << std::endl;
  std::vector<my_elem> v5(v4.cbegin(), v4.cend());

  std::cout << "6=====" << std::endl;
  std::vector<my_elem> v6(1);

  std::cout << "7=====" << std::endl;
  std::vector<my_elem> v7(1, 2);

  std::list<int> l{1, 2, 3, 4, 5, 6, 7};
  std::vector<double> vd(l.cbegin(), l.cend());
  std::vector<int> vi{1, 2, 3, 4, 5, 6, 7};
  std::vector<double> vd2(vi.cbegin(), vi.cend());

  std::string ele;
  std::deque<std::string> wq{10, ele};
  std::deque<std::string> wq2(wq);

  std::cout << "8=====" << std::endl;
  std::array<my_elem, 1> me;
}
