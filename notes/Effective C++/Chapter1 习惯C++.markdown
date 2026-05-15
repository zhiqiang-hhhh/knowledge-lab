[TOC]

## 少用 #define

`#define`与const的最大区别是，define并不会真正创建某个对象，因此也就不会有该对象的地址。

当我们需要取得一个 class 静态数据成员的地址时，必须为其创建定义式。

```c++
// Gameplayer.h
#include <iostream>

class Gameplayer {
private:
    static const int  NumTurns = 5;
    int scores[NumTurns];

public:
    void printAddress(){
        std::cout << "Address: " << &NumTurns << std::endl;
    }
};

// Gameplayer.cpp
#include "GamePlayer.h"

const int Gameplayer::NumTurns;

// main.cpp
#include "GamePlayer.h"

int main(){
    Gameplayer gameplayer{};

    gameplayer.printAddress();

    return 0;
}
```
`Gameplayer.h`中的`static const int  NumTurns = 5;`只是声明式，不会真的创建该对象。
`Gameplayer.cpp`中的`const int Gameplayer::NumTurns;`是定义式，由于在声明时已经赋了初值，所以这里不可以再设置初值。

若没有定义式，则会在编译时报错。
```bash
> g++ -O0  -o app GamePlayer.cpp main.cpp
Undefined symbols for architecture x86_64:
  "__ZN10Gameplayer8NumTurnsE", referenced from:
      __ZN10Gameplayer12printAddressEv in ccqVyYVw.o
ld: symbol(s) not found for architecture x86_64
collect2: error: ld returned 1 exit status
```

### enum hack
enum hack 实现的效果与#define相似，也不会创建具体对象（有时可以用此技术节省内存空间）。因此当我们不希望某个对象的地址被追踪时，可以使用 enum hack。

当 const 对象没有被追踪地址或者引用到时，优秀的编译器不会为其分配空间。

### inline 替代宏

使用#define定义宏充当函数的可读性非常差，而且容易出错。

```c++
#define CALL_WITH_MAX(a, b) f((a) > (b)) ? (a) : (b))
```
需要为宏内的所有实参添加小括号。且很容易出错！！！
```c++
int a = 5, b = 0;

CALL_WITH_MAX(++a, b);  // a 被累加两次
CALL_WITH_MAX(++a, b+10); // a 被累加一次
```
这种琐碎的事情很难注意到。使用 template inline ：
```c++
template<typename T>
inline void callWithMax(const T& a, const T& b)
{
    f(a > b ? a : b);
}
```

### 总结
- 对于单纯的常量，使用 const 对象或者 enum 替代 #define
- 对于形似函数的宏，使用 inline 函数

## Use const whenever possible
关于 const 的经典老番：
```c++
char greeting[] = "Hello";

char * p = greeting;        // non-const pointer, non-const data
const char* p = greeting;   // non-const pointer, const data
char* const p = greeting;   // const pointer, non-const data
const char* const p = greeting; // const pointer, const data
```

- const 出现在 * 左边：被指对象是常量
- const 出现在 * 右侧：指针本身是常量

### const 成员函数

如果两个成员函数只是 constness 不同，可以被重载。non-const 成员函数的第一个参数实际上是 `this`，const 成员函数的第一个参数实际上是 `const this`。

- bitwise-const：const 成员函数不更改对象的任何非 static 成员变量
- logical-const：const 成员函数可以修改对象的某些 bits，前提是不会被外部探测到

logical-const 的实现基础是 mutable 关键字：释放掉 non-static 成员变量的 bitwise constness 约束。即被 mutable 修饰的成员变量可以被 const 成员函数修改。

有时候，某个成员函数的 const 版本跟 non-const 版本做的事情完全一致，那么为了避免代码重复，我们可以在 non-const 函数成员中利用 const_cast + const 成员函数来实现减少冗余代码的目的：
```c++
class TextBlock{
public:
    ...
    const char& operator[](std::size_t position) const
    {
        ...
        ...
        ...
        return text[position];
    }
    char& operator[](std::size_t position)
    {
        return const_cast<char&>(
            static_cast<const TextBlock&>(*this)[position]
        );
    }
}
```
这里`static_cast`的目的是防止non-const自己调用自己。

注意，non-const 调用 const 是可考虑的，但是 const 调用 non-const 是不应该进行的。

### 总结
- 将某些东西声明为 const 可帮助编译器侦测出错误用法。const 可被施加于任何作用域内的对象、函数参数、函数返回类型、函数成员本体。
- 编译器实施 bitwise constness，但是编写程序时应当使用“概念上的常量性”
- 当 const 和 non-const 成员函数有着实质等价的实现时，另 non-const 版本调用 const 版本可避免代码重复。

## Item4 确保对象在使用前已经被初始化

确保每一个构造函数都将对象的每一个成员初始化。这里有两个点：
1. 使用成员初始化列表减少不必要的构造过程；
2. 了解变量初始化顺序会对程序稳定性造成的影响

### 成员初始化列表
注意区别赋值（assignment）和初始化（initialization）

对象成员的初始化动作发生在进入构造函数本体之前。
```c++
class PhoneNumber {...}
class ABEntry{
private:
    std::string theName;
    std::string theAddress;
    std::list<PhoneNumber> thePhones;
    int numTimeConsulted;

public:
    // 都是赋值而非初始化
    ABEntry(const std::string& name, const std::string& address, const std::list<PhoneNumber>& phones)
    {
        theName = name;
        theAddress = address;
        thePhones = phones;
        numTimesConsulted = 0;
    }
}
```
更好的做法，使用 member initialization list (成员初始值列表)
```c++
ABEntry(const std::string& name, const std::string& address, const std::list<PhoneNumber>& phones)
    : theName(name), theAddress(address), thePhones(phones), numTimesConsulted(0)
    {}
```

前一个过程：对于每一个数据成员类，调用其 default 构造函数进行初始化，然后再对他们进行赋值（assignment operator）。
后一个过程：对于每一个数据成员类，**调用一次**其 copy constructor，进行一次初始化。

假设 copy constructor 与 assignment operator 代价差不多，且一共 n 个成员变量，那么**使用成员初始化列表就可以省掉 n 次 default constructor**。

```c++
#include <iostream>

using namespace std;

class Foo {
    public:
        Foo() { std::cout << "Foo::Foo()\n"; }
        Foo(const Foo& foo1_) { std::cout << "Foo::Foo(const Foo&)\n"; }
        const Foo& operator=(const Foo&) {
            std::cout << "Foo::operator=(const Foo&)\n"; 
            return *this;
        }

};

class Bar {
    private:
        Foo foo;
    public:
        Bar() { std::cout << "Bar::Bar()\n"; }
        Bar(const Foo& foo_) : foo(foo_) {}
        // Bar(const Foo& foo_) {
        //    foo(foo_);
        // }
};

int main(){
    Foo foo;
    Bar bar(foo);
    return 0;
}
```
```bash
// initialization list
Foo::Foo()
Foo::Foo(const Foo&)

// non-initialization list
Foo::Foo()
Foo::Foo()
Foo::operator=(const Foo&)
```


另外，使用成员初始化列表可以保证对变量进行初始化，而不是在构造函数内对其进行赋值。当成员为const或者reference时这一点很重要：他们不能被赋值，只能被初始化。

C++有固定的类内成员初始化顺序：base classes总是早于其derived classes被初始化，而class的成员变量总是以其声明的顺序被初始化。比如初始化array需要指定其大小，那么代表大小的那个变量必须先有初值，此时其初始化顺序非常重要。

### 变量初始化顺序带来的影响
另一个需要关注的点是初始化顺序对于程序稳定性的影响。

static 对象：生命期从被构造出来到程序结束为止。包括global对象，定义于namespaces作用域内的对象、被static修饰的对象。
函数内的 static 对象：local-static 对象；非函数内的 static 对象：non local-static 对象


不同编译单元（.cpp文件）之间的 non-local static 对象的初始化次序并没有明确规定。因此，如果某个编译单元内的 non-local static 对象的初始化动作使用了另一个编译单元内的某个 non-local static 对象，它所用到的这个对象可能尚未被初始化。

C++保证，函数内的 local static 对象会在该函数被调用期间，首次遇到该对象的定义式之时，被初始化。

结合这两条，得出一条规则：将每个 non-local static 对象搬到自己的专属函数内（该对象在此函数内被声明为 static），这些专属函数返回一个reference指向它所包含的对象，然后用户通过调用这些专属函数来使用这些对象，而不是直接使用对象。实际上就是一个Singleton模式。这样保证调用者使用到这些对象时，对象已经被初始化。

### 总结
- 为内置类型对象进行手工初始化，因为C++不保证初始化它们
- 构造函数最好使用成员初始化列表，而不是在构造函数内使用赋值操作。一方面是减少开销，另一方面是确保进行初始化而不是赋值（reference以及const变量需要初始化）
- 为解决“跨编译单元之初始化次序”问题，请以local static对象替换non-local static对象

