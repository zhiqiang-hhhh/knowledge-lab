#include <iostream>
#include <string>

class Sales_data {
 public:
  Sales_data(const std::string& _s) : bookNo(_s), units_sold(0), revenue(0) {}
  std::string isbn() const { return bookNo; }
  unsigned changeUnits_Sold() { return ++units_sold; }
  // Sales_data& combine(const Sales_data&);
  void func() {}

 private:
  std::string bookNo;
  unsigned units_sold;
  double revenue;
};

int main() {
  Sales_data d1("d1");
  const Sales_data d2("d2");
  std::cout << d1.isbn() << std::endl;
  std::cout << d2.isbn() << std::endl;
  std::cout << d1.changeUnits_Sold() << std::endl;
  // std::cout << d2.changeUnits_Sold() << std::endl;
  
}