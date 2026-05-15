[TOC]
# Functions

返回类型不能是数组或者函数类型，但可以是指向函数的指针。

名字的作用域是程序文本的一部分，名字在其中可见。
名字的生命周期是程序执行过程中该对象存在的一段时间。


形参和函数体内部定义的变量统称为局部变量，仅在函数的作用域内可见。同时局部变量会隐藏在外层作用域中同名的其他所有声明。局部变量的声明周期依赖于定义的方式。

* 自动对象：只存在于块执行期间。对于局部变量对应的自动对象来说，初始化有两种方式：如果本身具有初始值，那就用初始值；否则执行默认初始化。
* 局部静态对象：局部静态对象在程序的执行路径第一次经过对象定义语句时初始化，并且直到程序终止才被销毁。如果局部静态对象没有显式初始化，那么它将执行值初始化（内置类型被0初始化，类类型默认初始化），内置类型的局部静态变量初始化为0。

### const 形参和实参
顶层const：对象本身是常量
底层const：指向的对象是常量

使用实参初始化形参时，会忽略顶层const。换句话说，形参的顶层const被忽略。当形参有顶层 const 时，给它传递常量对象或者非常量对象都是可以的。
```c++
void func(const int i){/* func 能够读取 i，但是不能向 i 写值 */}
void func(int i){ /*  */} // 错误：重复定义了 func(int)
```

重载的前提是不同函数的形参列表有区别。而因为顶层 const 被忽略，所以上述代码中传入两个 func 的参数可以完全一致。因此上述两个 func 的形参实际上没什么不同。

```c++
void func1(const int* i) { std::cout << *i; }  // 底层 const
void func1(int* const i) { std::cout << *i; }  // 顶层 const

// 形参的 const 不同，构成函数重载
```
### 指针或引用形参与const
可以使用非常量初始化一个底层 const，但是反过来不行；普通的引用必须用同类型的对象初始化
```c++
int i = 42;
const int *cp = &i;     // 正确
const *int cp2 = &i;    // 正确，cp2 与 cp 写法不同含义相同
const int &r = i;       // 正确
const int &r2 = 42;     // 正确
int *p = cp;    // 错误，p 和 cp 类型不匹配
int &r3 = r;    // 错误，r3 和 r 类型不匹配
int &r4 = 42;   // 错误，不能用字面值初始化一个非常量引用
```

### 含有可变形参的函数
无法预知应该向函数传递多少实参。

C++11提供两种主要方法：
* 如果所有的实参类型相同，那么可以传递一个名为`initializer_list`的标准库类型；
* 如果参数类型不同，使用可变参数模板

包含于头文件<initializer_list>中，**initializer_list**是一种标准库类型，用来表示某种特定类型的值的数组。
| 操作                               | 解释                                                                          |
| ---------------------------------- | ----------------------------------------------------------------------------- |
| initializer_list\<T> lst;          | 默认初始化；T类型元素的空列表                                                 |
| initializer_list\<T> lst{a,b,c...} | lst的元素是对应初始值的副本                                                   |
| lst2(lst); lst2 = lst;             | 拷贝；赋值一个initializer_list对象，其中的元素不会被拷贝，而是被lst2和lst共享 |
| lst.size()                         | 返回元素数量                                                                  |
| lst.begin(); lst.end()             | 返回首指针；返回尾指针                                                        |

`initializer_list`对象中的元素永远是常量，元素值无法改变。
```c++
void error_message(initializer_list<stirng> il){
    for(auto beg = il.begin(); beg != il.end(); beg++)
        cout << *beg << " ";
    cout << endl;
}

if(excepted != actual)
    error_message({"functionX", expected, actual});
else
    error_message({"functionX", "okey"});
```

如果想要向initializer_list形参中传递值序列，必须使用花括号。
**省略符形参**


## Pointers to Functions
函数指针是指向函数的指针，与其他类型一样，函数也有类型。函数的类型是其返回值类型+参数类型的组合，**函数名并不包含在内**。
```c++
// compares lengths of two strings
bool lengthCompare(const string &, const string &);
```
其类型为`bool (const string&, const string&)`，定义一个可以指向`lengthCompare`的函数指针:
```c++
// pf points to a function returning bool that takes two const string references
bool (*pf)(const string &, const string &); // uninitialized
```
当使用函数名作为值的时候，它可以自动被转换为一个相应类型的函数指针
```c++
pf = lengthCompare; // pf now points to the function named lengthCompare
pf = &lengthCompare; // equivalent assignment: address-of operator is optional
```
通过函数指针调用函数
```c++
bool b1 = pf("hello", "goodbye"); // calls lengthCompare
bool b2 = (*pf)("hello", "goodbye"); // equivalent call
bool b3 = lengthCompare("hello", "goodbye"); // equivalent call
```
当函数指针指向的函数具有重载时，需要在声明函数指针时就指定好对应的函数重载类型，后续通过该函数指针调用函数时，编译器将会根据函数指针类型来决定调用哪个函数重载版本
```c++
void ff(unsigned int);
void (*pf1)(unsigned int) = ff; // pf1 points to ff(unsigned)
void (*pf2)(int) = ff; // error: no ff with a matching parameter list
double (*pf3)(int*) = ff; // error: return type of ff and pf3 don't match
```
使用`decltype`简化声明
```c++
typedef bool Func(const string&, const string&);
typedef decltype(lengthCompare) Func2; // equivalent type

typedef bool(*FuncP)(const string&, const string&);
typedef decltype(lengthCompare) *FuncP2; // equivalent type
```