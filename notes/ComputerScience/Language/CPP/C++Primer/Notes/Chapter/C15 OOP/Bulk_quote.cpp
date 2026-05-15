#include <iostream>
#include <string>

class Quote {
 public:
  Quote() = default;
  Quote(const std::string &book, double sales_price)
      : bookNo(book), price(sales_price) {}
  std::string isbn() const { return bookNo; }
  virtual void test(std::string s = "Quote") const {
    std::cout << s << std::endl;
  }
  virtual double net_price(std::size_t n) const { return n * price; }
  virtual ~Quote() = default;
  virtual void debug() const {
    std::cout << this->bookNo << std::endl;
    std::cout << price << std::endl;
  }

  void memfun() {}

 private:
  std::string bookNo;

 protected:
  double price = 0.0;
};

class Bulk_quote : public Quote {
 public:
  Bulk_quote() = default;
  Bulk_quote(const std::string &, double, std::size_t, double);
  double net_price(std::size_t n) const override;
  void test(std::string s = "Bulk_quote") const override {
    std::cout << s << std::endl;
    std::cout << "Bulk_quote 1\n";
  }
  void debug() const override {
    Quote::debug();
    std::cout << min_qty << std::endl;
    std::cout << discount << std::endl;
  }

  void memfun(int i) {}

 private:
  std::size_t min_qty = 0;
  double discount = 0.0;
};

Bulk_quote::Bulk_quote(const std::string &book, double p, std::size_t qty,
                       double disc)
    : Quote(book, p), min_qty(qty), discount(disc) {}

double Bulk_quote::net_price(std::size_t n) const {
  double res;
  if (n >= min_qty)
    res = price * (1 - discount) * n;
  else
    res = n * price;
  return res;
}

double print_total(std::ostream &os, const Quote &item, std::size_t n) {
  double ret = item.net_price(n);
  os << "ISBN: " << item.isbn() << " # sold: " << n << " total due: " << ret
     << std::endl;
  return ret;
}

int main() {
  Quote *item1 = new Quote("C++ Primer", 45);
  Bulk_quote item2 = Bulk_quote("C++ Primer PLUS", 40, 100, 0.3);
  item1->debug();
  item1 = &item2;
  item1->debug();
  item1->Quote::memfun();
  item2.Quote::memfun();
}