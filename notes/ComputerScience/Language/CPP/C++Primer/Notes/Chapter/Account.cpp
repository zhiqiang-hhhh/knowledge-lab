#include<iostream>
#include<string>
using namespace std;

class Account
{
public:
    void calculate() { amount += amount * interestRate; }
    static double rate() { return interestRate; }
    static void rate(double);

private:
    string owner;
    double amount;
    static double interestRate;
    //静态成员函数不与任何类对象绑定，因此不包含this指针
    //所以静态成员函数不能被声明为const
    static double initRate();
};
//静态数据成员不能在类地内部被定义，必须在类的外部定义和初始化每个静态成员
double Account::interestRate = Account::initRate();

void Account::rate(double newrate)
{
    interestRate = newrate;
}

int main()
{
    double r;
    r = Account::rate();
}