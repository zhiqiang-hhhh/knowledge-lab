# Copy assign operator
```cpp
class CMyString1 {
public:
    CMyString1(char* pData = nullptr);
    CMyString1(const CMyString& str);
    ~CMyString1();
    CMyString1& operator=(const CMyString1& str) {
        if (this == &str) {
            return *this;
        }
        
        delete[] m_pData;
        m_pData = new char[strlen(str.m_pData) + 1];
        strcpy(m_pData, str.m_pData);
        return *this;
    }
private:
    char* m_pData;
};
```
这个版本能够完成基本功能：
1. 返回一个mutable reference
2. 入参类型是 const reference

但是无法保证内存安全：当 new 分配内存失败后会抛出异常，导致当前对象的状态非法。

```cpp
class CMyString2 {
public:
    CMyString2(char* pData = nullptr);
    CMyString2(const CMyString2& str) {
        m_pData = new char[strlen(str.m_pData) + 1];
        strcpy(m_pData, str.m_pData);
    }

    ~CMyString2() {
        delete [] m_pData;
    }

    CMyString2& operator=(const CMyString2& str) {
        if (this == &str) {
            return *this;
        }
        
        CMyString2 temp(str);
        std::swap(m_pData, temp.m_pData);
        return *this;
    }

private:
    char* m_pData;
};
```
`CMyString2` 的修改：
1. 在拷贝构造函数里完成内存分配与复制
2. 拷贝赋值运算符里面先构造一个局部`CMyString2`变量，然后把改临时对象的内存指针与当前对象的内存指针做交换，利用临时对象来释放当前对象之前分配的内存。

如果内存分配失败，那么当前对象的状态不会被影响。并且利用 RAII 实现内存安全与异常安全。

# Copy and swap
前面实现拷贝赋值运算符的策略叫做 copy-and-swap。是 cpp 里一种常见的保证异常安全的资源替换策略。
不只是 copy-assign operator，只要是某个类包含复杂的资源，那么当我们需要修改其状态时就可以用 copy-and-swap 实现，比如
```cpp
class Config {
public:
    void setName(const std::string& newName) {
        std::string tmp(newName);
        name_.swap(tmp);
    }
private:
    std::string name_;
};
```

# std::move

copy and swap 很好，但是有一个问题是如果入参的对象是一个临时对象呢？此时对一个临时对象进行深拷贝是没必要的。

C++11 引入 std::move + 移动构造函数。

```cpp
public:
  CMyString3(char *pData = nullptr) {
    if (pData) {
      m_pData = new char[strlen(pData) + 1];
      strcpy(m_pData, pData);
    } else {
      m_pData = new char[1];
      m_pData[0] = '\0';
    }
  }

  CMyString3(const CMyString3 &str) {
    std::cout << "Copy constructor called" << std::endl;
    m_pData = new char[strlen(str.m_pData) + 1];
    strcpy(m_pData, str.m_pData);
  }

  CMyString3(CMyString3 &&str) noexcept {
    std::cout << "Move constructor called" << std::endl;
    m_pData = str.m_pData;
    str.m_pData = nullptr;
  }

  CMyString3 &operator=(const CMyString3& str) {
    std::cout << "Copy assignment operator called." << std::endl;
    CMyString3 temp(str);
    std::swap(temp.m_pData, this->m_pData);
    return *this;
  }

  CMyString3 &operator=(CMyString3&& str) noexcept {
    std::cout << "Move assignment operator called" << std::endl;
    std::swap(m_pData, str.m_pData);
    return *this;
  }

  ~CMyString3() { delete[] m_pData; }

private:
  char *m_pData;
};

int main() {
  CMyString3 str1("Hello");
  CMyString3 str2("World");
  std::cout << "Before move" << std::endl;
  str2 = str1;
  std::cout << "Do move" << std::endl;
  str2 = std::move(str1);
  return 0;
}
```
上述代码里实现了移动构造函数，重载实现了两个拷贝赋值运算符。
执行的结果为
```bash
Before move
Copy assignment operator called.
Copy constructor called
Do move
Move assignment operator called
```
当入参为lvalue时，走的是 copy-and-swap 路线，当入参为rvalue时，走的是移动拷贝赋值运算符。

# 最佳实践
上述代码虽好，但是写法很繁琐，你需要手动写两个赋值运算符。将移动赋值运算符的入参改成按值传递，那么就可以同时获得具有移动语意和复制语意的运算符。
```cpp
class CMyString4 {
public:
  CMyString4(char *pData = nullptr) {
    if (pData) {
      m_pData = new char[strlen(pData) + 1];
      strcpy(m_pData, pData);
    } else {
      m_pData = new char[1];
      m_pData[0] = '\0';
    }
  }

  CMyString4(const CMyString4 &str) {
    std::cout << "Copy constructor called" << std::endl;
    m_pData = new char[strlen(str.m_pData) + 1];
    strcpy(m_pData, str.m_pData);
  }

  CMyString4(CMyString4 &&str) noexcept {
    std::cout << "Move constructor called" << std::endl;
    m_pData = str.m_pData;
    str.m_pData = nullptr;
  }

  CMyString4 &operator=(CMyString4 str) noexcept {
    std::cout << "Move assignment operator called" << std::endl;
    std::swap(m_pData, str.m_pData);
    return *this;
  }

  ~CMyString4() { delete[] m_pData; }

private:
  char *m_pData;
};

int main() {
  CMyString4 str1("Hello");
  CMyString4 str2("World");
  std::cout << "Before move" << std::endl;
  str2 = str1;
  std::cout << "Do move" << std::endl;
  str2 = std::move(str1);
  return 0;
}
```
运行结果：
```bash
Before move
Copy constructor called
Move assignment operator called
Do move
Move constructor called
Move assignment operator called
```
对于lvalue，首先执行copy construction，得到一个临时变量，然后在 operator= 执行 swap。
对于rvalue，首先执行move construction，得到一个临时变量，然后在 operator= 执行 swap。

简化了写法，代价为增加了一次 move constructor 的调用，然而该函数只执行了一次 std::swap 操作，代价很小。