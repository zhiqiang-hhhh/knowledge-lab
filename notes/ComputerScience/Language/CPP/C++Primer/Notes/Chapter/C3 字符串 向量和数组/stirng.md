<!-- TOC -->

- [string](#string)
  - [[TOC]](#toc)
  - [string 的构造函数](#string-%e7%9a%84%e6%9e%84%e9%80%a0%e5%87%bd%e6%95%b0)
  - [读写 string 对象](#%e8%af%bb%e5%86%99-string-%e5%af%b9%e8%b1%a1)
  - [string::size_type](#stringsizetype)
  - [string 的操作](#string-%e7%9a%84%e6%93%8d%e4%bd%9c)
    - [比较](#%e6%af%94%e8%be%83)
    - [相加](#%e7%9b%b8%e5%8a%a0)
  - [操作string中的字符](#%e6%93%8d%e4%bd%9cstring%e4%b8%ad%e7%9a%84%e5%ad%97%e7%ac%a6)
    - [cctype](#cctype)
    - [范围 for 语句](#%e8%8c%83%e5%9b%b4-for-%e8%af%ad%e5%8f%a5)
    - [下标运算符](#%e4%b8%8b%e6%a0%87%e8%bf%90%e7%ae%97%e7%ac%a6)

<!-- /TOC -->

# string 
[TOC]
---
## string 的构造函数
```c++
string s1;  // 默认初始化，空串
string s2 = s1; // 拷贝初始化, s2 是 s1 的副本
string s3("Value"); // 直接初始化，s3 是该C风格字符串的副本
string s4(10,'c');  // 直接初始化，s4 内容为10个 c 字符串
```
## 读写 string 对象

cin >> 或者使用 string 头文件中的 getline 函数

这两种方式都不保存结束符；

前者以空白(空格、换行、制表符)作为结束符，后者以换行符为结束符。



## string::size_type 

string::size_type 体现了标准库的与机器无关的特性。

string::size_type 一定是一个无符号类型的值，因此在表达式中使用 string::size_type 时一定要注意不能和有符号数混合使用。因为有符号数和无符号数在表达式中混用时，有符号数的机器表示不变，直接被解读成一个无符号数。这样，一个负的有符号数就会被解读成一个非常大的无符号数。


## string 的操作
### 比较

比较是按照字典顺序比较的。

### 相加
可以是两个 string 对象相加，也可以是 string 对象和字面值相加。
## 操作string中的字符

### cctype
建议在 C++ 中引用 **C 标准库**时，将 C 标准库的头文件的 .h 去掉，在头添加 c。
```c++
#include <ctype.h>  // C语言中使用头文件的方式
#include <cctype>   // 符合C++ 命名规范的头文件使用形式，效果与上面一样
```
头文件 cctype 中定义了一组标准库函数处理字符的特性

### 范围 for 语句

适合访问单个字符

### 下标运算符

**接收的参数为 string::size_type 类型的参数**

可以访问指定位置的元素，返回的是该元素的引用。
前提是指定位置元素存在

**不能使用下标运算符来向string中添加元素**
