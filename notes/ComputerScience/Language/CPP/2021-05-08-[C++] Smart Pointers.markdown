# 智能指针

    Modern Effective C++

裸指针的缺点：
1. 单从指针类型无法得知指针到底指向一个简单对象还是一个数组；
2. 无法从指针声明了解当前过程是否拥有该指针，结果就是不知道在使用完成后是否应当释放指针指向的资源；
3. 就算你知道应当删除对应的资源，你也不知道是应该通过简单的delete还是应当使用其他自定义的删除方式；
4. 就算你知道应当使用delete，你也有可能搞不清是否应该添加`[]`
5. 就算你知道应当怎么删除，你也很难保证删除行为只被执行了一次；
6. 通常很难判断某个指针是否为`dangles`指针（悬空指针）。Dangling pointers arise when objects are destroyed while pointers still point to them.

## Use `std::unique_ptr` for exclusive-ownership resource management
典型用途：工厂模式的返回值。
```c++
class Investment { ... };

class Stock: public Investment { ... };

class Bond: public Investment { ... };

class RealEstate: public Investment { ... };

template <typename... Ts>
std::unique_ptr<Investment>
makeInvestment(Ts&&... params);
```
可以在`unique_ptr`构造的时候为对象指定资源回收方式。
```c++
auto delInvmt = [](Investment* pInvestment) // custom
                { // deleter
                    makeLogEntry(pInvestment); // (a lambda
                    delete pInvestment; // expression)
                };
template<typename... Ts> // revised
std::unique_ptr<Investment, decltype(delInvmt)> // return type
makeInvestment(Ts&&... params)
{
    std::unique_ptr<Investment, decltype(delInvmt)> // ptr to be
    pInv(nullptr, delInvmt); // returned

    if ( /* a Stock object should be created */ ){
        pInv.reset(new Stock(std::forward<Ts>(params)...));
    } else if ( /* a Bond object should be created */ ) {
        pInv.reset(new Bond(std::forward<Ts>(params)...));
    } else if ( /* a RealEstate object should be created */ ) {
        pInv.reset(new RealEstate(std::forward<Ts>(params)...));
    }
    
    return pInv;
}
```
从裸指针到`unique_ptr`的隐式类型转换是不被允许的。
```c++
template<typename... Ts>
auto makeInvestment(Ts&&... params) // C++14
{
auto delInvmt = [](Investment* pInvestment) // this is now
{ // inside
makeLogEntry(pInvestment); // makedelete
pInvestment; // Investment
};
std::unique_ptr<Investment, decltype(delInvmt)> // as
pInv(nullptr, delInvmt); // before
if ( … ) // as before
{
pInv.reset(new Stock(std::forward<Ts>(params)...));
}
... // as before
}
```
通常来说`std::unique_ptr`的大小与裸指针一样大，但是当使用自定义deleters时，`std::unique_ptr`的大小**通常**会变为两个裸指针。对于deleters使用函数对象的情况，具体大小取决于函数对象中存储了多少状态。比如，对于无状态函数对象（capture list为空的lambda expression），它们不会导致`std::unique_ptr`的大小变大，因此能用stateless lambda expression就用。
```c++
auto delInvmt1 = [](Investment* pInvestment) // custom
{ // deleter
makeLogEntry(pInvestment); // as
delete pInvestment; // stateless
}; // lambda
template<typename... Ts> // return type
std::unique_ptr<Investment, decltype(delInvmt1)> // has size of
makeInvestment(Ts&&... args); // Investment*
void delInvmt2(Investment* pInvestment) // custom
{ // deleter
makeLogEntry(pInvestment); // as function
delete pInvestment;
}
template<typename... Ts> // return type has
std::unique_ptr<Investment, // size of Investment*
void (*)(Investment*)> // plus at least size
makeInvestment(Ts&&... params); // of function pointer!
```