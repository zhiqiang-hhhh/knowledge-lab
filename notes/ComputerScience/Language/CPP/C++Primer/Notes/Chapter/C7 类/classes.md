[TOC]
---
## 定义成员函数

### **引入 this**
成员函数通过隐含的额外的 this 指针来访问调用该函数的对象。

const 成员函数：const 跟在参数参数列表之后，const 的目的在于限定隐含的 this 指针的类型。

默认情况下，const是一个 const pointer，which pointes to a **non-const version** of class type. 

因此，默认情况下，const 对象不能调用 ordinary member function：因为传递给成员函数的 const 类对象的 this 指针是通过取地址运算符得到的，对 const 对象取地址得到的指针为底层 const 指针，ordinary member function 的隐含 this 指针参数类型为普通指针，底层 cosnt 指针无法转换为普通指针，所以参数类型不匹配。
```c++
class my_class{
    ...
  public:
    void func() const;  // 相当于函数声明为伪代码 func(const my_class* const this);
                        // 前一个 const 为底层 const，后一个 const 为顶层 const
    void func2();   // 相当于函数声明为伪代码 func(my_class* const this); const 为顶层 const
    ...
};

    my_class c1;
    const my_class c2;
    c1.func();  // 正确：相当于伪代码 func(&c1); &c1 得到的指针类型为 my_class* const，普通指针
    c2.func();  // 正确：相当于伪代码 func(&c2); &c2 得到的指针类型为 const my_class* const
    c1.func2(); // 正确

    c2.func2(); // 错误：形参类型为 my_class* const, 实参类型为 const my_class* const, 实参无法转换为形参

}
```
### 类作用域和成员函数
编译器首先编译成员的声明，然后才轮到成员函数体（如果有的话）。因此成员函数体中可以随意使用类中的其他成员而不用管成员出现的顺序。

当在类的外部定义成员函数时，首先通过作用域运算符说明后面的代码块位于指定类的作用域中，在外部定义成员函数时，就可以直接使用类内部定义的成员。

## 构造函数
构造函数用来控制类对象的初始化过程。无论何时，只要类对象被创建，构造函数就会被调用。

不接受任何参数的构造函数——默认构造函数
**当且仅当类不包含任何构造函数声明**的情况下，编译器会创建合成默认构造函数。

**default** 关键字，作用是要求编译器生成一个合成拷贝构造函数。当我们定义了其他构造函数的同时，希望让默认构造函数的行为和合成拷贝构造函数一致时，可以使用default关键字。

## 类的其他特性
### 可变数据成员
一个可变数据成员永远不会是const，即使它是const对象的成员, 使用 mutable 关键字来修饰成员.