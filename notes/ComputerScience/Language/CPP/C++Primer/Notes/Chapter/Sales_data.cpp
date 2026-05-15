#include<iostream>
#include<string>

class Sales_data{
public:
    explicit Sales_data(const std::string &s = " ") : bookNo(s){};// 默认构造函数
    Sales_data(const Sales_data &);//拷贝构造函数
    Sales_data(const std::string &s, unsigned n, double p) : bookNo(s), units_sold(n), revenue(p*n){}
    explicit Sales_data(std::istream &is);
    Sales_data &operator=(const Sales_data &);

    std::string isbn() const { return bookNo; }
    Sales_data &combine(const Sales_data &);
    double avg_price() const;

private:
    std::string bookNo;
    unsigned units_sold = 0;
    double revenue = 0.0;
};

Sales_data::Sales_data(const Sales_data &s) : 
    bookNo(s.bookNo), 
    units_sold(s.units_sold),
    revenue(s.revenue)
    {}

Sales_data::Sales_data(std::istream &is){
    double p = 0.0;
    is >> bookNo;
    is >> units_sold;
    is >> p;
    revenue = p * units_sold;
}
Sales_data& Sales_data::operator=(const Sales_data &rhs){
    bookNo = rhs.bookNo;
    units_sold = rhs.units_sold;
    revenue = rhs.revenue;
    return *this;
}

Sales_data &Sales_data::combine(const Sales_data &sd){
    units_sold += sd.units_sold;
    revenue += sd.revenue;
    return *this;
}

double Sales_data::avg_price() const{
    return revenue / units_sold;
}