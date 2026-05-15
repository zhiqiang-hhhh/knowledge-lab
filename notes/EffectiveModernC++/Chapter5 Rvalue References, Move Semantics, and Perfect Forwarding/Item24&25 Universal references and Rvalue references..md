## Item24
当 && 与模版参数在一起时，需要准确区分该参数具体是右值引用还是万能引用(universal references)，这关系到实例化的时候到底与什么类型实参绑定。

当 T 是一个需要推导的类型时，T&& 表示参数是一个万能引用——既可以绑定左值引用也可以绑定右值引用。其他情况下 T&& 表示右值引用（T是一个具体的类型）。

万能引用通常在两种情况下出现：
1. 函数模板的形参
```c++
template<typename T>
void f(T&& param);
```
2. auto&&
```c++
auto&& var2 = var1;
```

万能引用的条件比较“苛刻”，也许可以认为只有严格为上述格式的 && 才是万能引用，稍有差别便会变为右值引用。
```c++
template<typename T>
void f(std::vector<T>&& param); // 右值引用

template<typename T>
void f(const T&& param);    // 右值引用
```
当 T&& 出现在模板类的模板函数形参时，T&& 往往是一个右值引用**而不是万能引用**。因为模板类被实例化之后，T&& 便不再涉及到类型推导。


但是也有例外，当模板类具有一个模板函数，而该模板函数的模板参数并不来自于模板类的模板参数时，T&& 又回变为万能引用，比如：
```c++
template<typename T, typename Allocator = allocator<T>>
class vector {
public:
    template <class... Args>
    void emplace_back(Args&&... args);
}
```
这里的 emplate_back 的形参是万能引用，因为类型参数 Args 只有在 emplace_back 被真正调用时才会被推导，与模板类的类型参数 T 无关。

## Item25
我们知道 std::move 的使用动机是将一个已知的可移动对象传递给某个函数，使得其能够利用到该对象的可移动特性。而universal reference 既可能绑定的一个 lvalue reference 也可能绑定 rvalue reference，那么当我们想要利用来自 universal reference 的 rvalue reference 时，该怎么保持该实参的特性呢？答案是 std::forward

```c++
class Widget {
public:
    template<typename T>
    void setName(T&& newName) // universal reference
    { name = std::forward<T>(newName); }
}
```
一种想当然的对 std::forward 的替代想法是针对 lvalue reference 和 rvalue reference 写不同的重载函数。
比如：
```c++
class Widget {
public:
    void setName(const string& newName) 
    { name = newName; }
    void setName(std::string&& newName) 
    { name = std::move(newName); }
}
```
一个显而易见的问题是代码变多了，不好维护。还有会带来运行期的效率问题，考虑
```c++
w.setName("Adela Novak");
```
如果使用模板类型推导，那么 T -> const char*，在调用 setName 时不会创建 std::string 对象，减少了构造与析构的代价。

除了上述问题，针对具体类型左值右值分别重载最大的问题是扩展性太差，假如具体类型有10个呢？