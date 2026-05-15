#include<string>
#include<iostream>

//类值
class HasPtr{
public:
    HasPtr(const std::string &s = std::string()):
        ps(new std::string(s)), i(0){}
    HasPtr(const HasPtr &s):
        ps(new std::string(*s.ps)), i(s.i){}

    HasPtr &operator=(HasPtr);
    HasPtr &operator=(const std::string &);
    std::string &operator*();

    friend void swap(HasPtr &, HasPtr &);
    ~HasPtr(){ delete ps; }

private:
    std::string *ps;
    int i;
};    

HasPtr& HasPtr::operator=(HasPtr s)
{
    swap(*this, s);
    return *this;
}

HasPtr& HasPtr::operator=(const std::string &s)
{
    *ps = s;
    return *this;
}

std::string &HasPtr::operator*()
{
    return *ps;
}

void swap(HasPtr& lhp, HasPtr& rhp)
{
    using std::swap;
    swap(lhp.ps, rhp.ps);
    swap(lhp.i, rhp.i);
}



class number{ 
public:
    number(): index(gindex+=1) {}
    number(const number &s): index(gindex+=1) {}

    friend void f(const number &s) { std::cout << s.index << std::endl; }
    //friend void f(number s) { std::cout << s.index << std::endl; }
private:
    static int gindex;
    int index;
};
int number::gindex = 0;

int main()
{
    HasPtr h("hi mom!");
    HasPtr h2(h);
    HasPtr h3 = h2;

    std::cout << *h2 << std::endl;

    h2 = "hi dad!";
    h3 = "hi sin!";

    std::cout << *h << std::endl;
    std::cout << *h2 << std::endl;
    std::cout << *h3 << std::endl;

    return 0;
}
