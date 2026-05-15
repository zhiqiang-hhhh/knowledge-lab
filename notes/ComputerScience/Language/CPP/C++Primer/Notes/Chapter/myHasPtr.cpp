#include<string>
#include<iostream>

class myHasPtr{
private:
    std::string *ps;
    int i;
    std::size_t *use;
public:
    myHasPtr(const std::string& s = " ") : //默认构造函数
        ps(new std::string(s)), i(0), use(new std::size_t(1)) {}
    myHasPtr(myHasPtr &s) : 
        ps(s.ps), i(s.i), use(s.use) { ++*s.use; }

    myHasPtr &operator=(const std::string &s);
    myHasPtr &operator=(const myHasPtr &);
    std::string operator*() { return *ps; }

    std::size_t used() { return *use; }
    const std::string &mystring() { return *ps; }
    ~myHasPtr();

    friend void swap(myHasPtr &, myHasPtr &);
};

myHasPtr &myHasPtr::operator=(const std::string& s){
    if(--*use == 0){
        delete ps;
        delete use;
    }

    ps = new std::string(s);
    use = new std::size_t(1);

    return *this;
}

myHasPtr &myHasPtr::operator=(const myHasPtr& s){
    ++*s.use;
    if(--*use == 0){
        delete ps;
        delete use;
    }
    
    ps = s.ps;
    use = s.use;
    i = s.i;

    return *this;
}

myHasPtr::~myHasPtr(){
    if(--*use == 0){
        delete ps;
        delete use;
    }
}

void swap(myHasPtr& lhs, myHasPtr& rhs)
{
    using std::swap;
    swap(lhs.ps, rhs.ps);
    swap(lhs.i, rhs.i);
}


int main(){
    myHasPtr h1("test");
    myHasPtr h2("test2");
    swap(h1, h2);
    std::cout << h1.mystring() << std::endl;
}