# 构造/析构/赋值运算

## C++默认添加了哪些函数
- 如果程序员自己没有声明，那么C++编译器就会为该类声明一个copy构造函数、一个copy assignment操作符和一个析构函数。
- 如果程序员没有声明任何构造函数，那么C++编译器还会声明一个default构造函数。
- 如果某个class的base class自身声明有virtual析构函数，那么编译器自动生成的析构函数也是virtual，否则则为non-virtual


## 为多态基类声明virtual析构函数

当 drived class 对象经由一个 base class 指针被删除，而该 base class 带着一个 non-virtual 析构函数，其结果未有定义——实际执行时通常发生的是对象的 derived 成分没有被销毁。

任何 class 带有 virtual 函数都几乎确定应该也有一个 virtual 析构函数。

对于不会被当作 base class 使用的类，则绝对不要轻易为其添加 virtual 函数：这会为该类创建虚函数表，虚函数表指针，改变该类对象的内存布局。假如在一个32bits的计算机体系结构中，一个对象本身只占用32bit，那么添加 virtual 函数后，其占用空间将会变为 32+32 = 64 bits。

析构函数的运行方式：最深层派生（most derived）的那个 class 其析构函数最先被调用，然后是其每一个 base class 的析构函数被调用。

## 别让异常逃离析构函数

假如某个类的析构函数会抛出异常，若在某个栈帧内有多个该类的对象，那么栈帧被回收，对象被析构时，就会可能同时出现两个异常。在两个异常同时出现存在的情况下，程序若通常会导致不明确的行为。

假如析构函数必须执行某个可能会导致异常抛出的动作，那么通常来说，强迫程序终止是一个合理的选项。
```c++
DBConn::~DBConn()
{
    try
    { 
        db.close();
    }
    catch (...)
    {
        std::abort();
    }
}
```
更好的选择：提供`DBConn::Close()`函数，要求调用者去主动处理该异常。

## 绝不在构造和析构的过程中使用virtual函数
```c++
class Transaction{
public:
    Transaction();
    virtual void logTransaction() const = 0;

    ...
};

Transaction::Transaction()
{
    ...
    logTransaction();
}

class BuyTransaction : public Transaction()
{
public:
    virtual void logTransaction() const;
    ...
}
class SellTransaction: public Transaction()
{
public:
    virtual void logTransaction() const;
    ...
}
```


在 base class 构造期间 virtual 函数绝不会下降到 derived classes 阶层。因此此时调用 virtual function 或者 pure virtual function 是危险的。因为 derived class 的成员可能并未被初始化。

**在 derived class 对象的 base class 构造期间，对象的类型是 base class 而不是 derived class**

如果确实需要在 class Transaction 的构造/析构函数中调用 logTransaction，那么正确的做法是将其替换为 non-virtual 版本，然后要求 derived class 构造函数传递必要信息给 Transaction 构造函数。

```c++
class Transaction
{
public:
    explicit Transaction(const std::string& logInfo);
    void logTransaction(const std::string& logInfo) const;

    ...
};

Transaction::Transaction(const std::string& logInfo)
{
    ...
    logTransaction(logInfo);
}

class BuyTransaction : public Transaction
{
public:
    BuyTransaction(parameters) : Transaction(createLogString(parameters))
    {...}
    ...
private:
    static std::string createLogString(parameters);
}
```

## 在 operator = 中处理自我赋值

当某个类需要实现 `operator=` 时，通常必须考虑自我赋值的情景。

自我赋值通常发生在不明显的情形下。

```c++
class Bitmap { ... };
class Widget {
    ...
private:
    Bitmap* pb;
};

Widget&
Widget::operator=(const Widget& rhs)
{
    delete pb;
    pb = new Bitmap(*rhs.pb);
    return *this;
}
```
这里如果 rhs 与 this 都指向同一个对象，那么就会导致访问一个已经被删除的对象。

传统的解决方法：identify test
```c++
Widget& Widget::operator=(const Widget& rhs)
{
    if (this == &rhs) return *this; // identify test

    delete pb;
    pb = new Bitmap(*rhs.pb);
    return *this;
}
```
另一个解法：在复制pb所指对象之前不要删除pb
```c++
Widget& Widget::operator=(const Widget& rhs)
{
    Bitmap* pOrig = pb;
    pb = new Bitmap(*rhs.pb);
    delete pOrig;
    return *this;
}
```
另一个解法，利用 copy and swap
```c++
class Widget{
    ...
    void swap(Widget& rhs);
    ...
};
Widget& Widget::operator=(const Widget& rhs)
{
    Widget temp(rhs);
    swap(temp);
    return *this;
}
```
另一个解法，利用by value传参实现复制
```c++
Widget& Widget::operator=(WIdget rhs)
{
    swap(rhs);
    return *this;
}
```

## 复制对象时记得复制基类成员
当编写 copying 函数（copy consttuctor，copy assignment operator）时，确保：
1. 复制所有 local 成员变量
2. 调用所有 base classes 内的适当的 copying 函数