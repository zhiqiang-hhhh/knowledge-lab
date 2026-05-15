### 使用 CRTP 包装你的大脑
1995 年，`James Coplien` 在 `C++ Report` 上的一篇文章第一次引入 CRTP 这个名字。
#### virtual function 的问题
性能开销是虚函数的最大问题。虚函数的调用成本可能数倍于非虚函数，对于那些很简单的可以被 inline 的方法来说，这种代价可能更高（虚函数无法被 inline）。
#### Introducing CRTP
```cpp
template <typename D> class B {
    ...
};

class D : public B<D> {
    ...
}
```
基类被改成了一个 class template，子类依然继承自基类，但是继承的是基类的一个特殊实例化，这个特殊实例是用子类类型进行实例化的。

Class B is instantiated on class D, and class D inherits from that instantiation of class B, which
is instantiated on class D, which inherits from class B, which... that’s recursion in action.

从这一段描述可以看到 CRTP 名字的由来。

```cpp
// Example 01
template <typename D> class B {
    public:
        B() : i_(0) {}
        void f(int i) { static_cast<D*>(this)->f(i); }
        int get() const { return i_; }
    protected:
        int i_;
};
class D : public B<D> {
    public:
        void f(int i) { i_ += i; }
};
```
##### Restriction
The main restriction on the CRTP is that the size of the base class, B, cannot depend on its template parameter, D. More generally, the template for class B has to instantiate with type D being an incomplete type. For example, this will not compile:
```cpp
template <typename D> class B {
    using T = typename D::T;
    T* p_;
};
class D : public B<D> {
    using T = int;
};
```
上述代码无法编译的事实可能会有点令人惊讶，因为使用模板参数类型作为成员变量是很常见的，比如
```cpp
template <typename C> class stack {
        C c_;
    public:
        using value_type = typename C::value_type;
        void push(const valuetype& v) { c.push_back(v); }
        value_type pop() {
            value_type v = c.back();
            c.pop_back();
            return v;
        }
};

stack<std::vector<int>> s;
```
上述代码实际上可以正常编译
```cpp
class A {
    public:
    using T = int;
    T x_;
};

B<A> b;
```
事实上，CRTP 中的问题不在 class B 本身，而在于我们使用 B 的方式：
```cpp
class D : public B<D> ...
```
At the point where `B<D>` has to be known, type `D` has not been declared yet. 当编译器遇到 class D 的声明的时候，它需要知道基类 `B<D>` 是什么，因此，如果 D 还没有被声明完成，那么编译器就无法知道 D 指向的类型。上述的问题与如下代码的本质是一样的
```cpp
class A;
B<A> b; // Now does not compile.
```
有时候模板是可以通过前向声明的类型实例化的，然而有些却不行。这一规则的核心是：任何影响到类本身大小的东西必须要被 fully declared。引用某个 incomplete type 的嵌套类型相当于是对这个嵌套类型的前向声明
A reference to a type declared inside an incomplete type, such as our using T = typename D::T, would be a forward declaration of a nested class, and those are not allowed either.
##### Another finding
类模板的成员函数的 body 直到它被调用的时候才会被实例化。
事实上，对于一个给定的模板参数，如果他没有被调用，那这类成员函数甚至都不需要被编译。

那么，有一个有趣的事情是，通过基类的成员函数，我们可以完美地使用子类的类型，哪怕它是一个 incomplete type。并且由于 derived class 以及它的嵌套类型都被前向声明了，那么我们可以在基类的成员函数里安全地使用指向他们的指针/引用。

这里有一个对 CRTP 基础类的非常通用的重构，这个重构把 static cast 固定到了一个位置：
```cpp
template <typename D> class B {
    ...
    void f(int i) { derived()->f(i); }
    D* derived() { return static_cast<D*>(this); }
};

class D : public B<D> {
    ...
    void f(int i) { i_ += i; }
};
```
这里基类声明使用了对某个 incomplete incomplete (forward-declared) type D 的指针。这个指针看起来跟其他指向 incomplete type 的指针一样，当指针被解引用的时候，类型一定要是完整的。

##### Use the finding to sovle the restriction
那么当我们需要在基类中使用继承类及其嵌套类型时，我们应该怎么做呢？
在函数体中，这毫无问题。
但是如果我们要在 base class itself 中使用嵌套类型，那么这分为两种情况。
1. 在返回值中使用嵌套类型
```cpp
template <typename D> class B {
    typename D::value_type get() const {
        return static_cast<const D*>(this)->get();
    }
    ...
};

class D : public B<D> {
    using value_type = int;
    value_type get() const {...}
}
```
此时需要把基类中的返回值类型改成 auto，至于为啥，暂时找不到让人明白原因的解释。
chatgpt 说如果手动指定类型，那么编译器需要在编译 `B<D>` 的时候知道 D 的完整定义，而 D 的完整定义又需要等到 `B<D>` 定义完成，这就出现了类型依赖，而写成 auto 就可以让编译器等待 D 定义完成后再自动推导 get 的类型。

我的疑问是为什么手动指定类型的时候，编译器就不能使用和 auto 一样的策略去做呢？

2. 需要把嵌套类型用作数据成员或者参数
此时必须额外增加一个模板参数。
```cpp
// Example 01a
template <typename T, typename value_type> class B {
    value_type value_;
    …
};
class D : public B<D, int> {
    using value_type = int;
    value_type get() const { … }
    …
};
```
#### CRTP and static polymorphism
通过 CRTP 我们可以在子类中实现基类的方法，这实际上是一种多态行为，相比运行时多态，这种多态是在编译期实现的。
##### Compile-time polymorphism
```cpp
template <typename D> class B {
    public:
    ...
    void f(int i) { static_cast<D*>(this)->f(i); }
    protected:
    int i_;
};
class D : public B<D> {
    public:
    void f(int i) { i_ += i; }
};
```
当 B::f() 方法被调用的时候，它会把函数调用分发到实际的继承类的方法上，效果和虚函数一样。
```
D* d = ...; // Get an object of type D
d->f(5);
B<D>* b = ...; // Also has to be an object of type D
b->f(5);
```
与虚函数调用的最大区别在于，继承类 D 的定义需要在编译时期就被看到。因为实际的基类指针是 `B<D>*` 而不是 `B*`。
对于程序员来说，这种形式的多态似乎没什么意思，但是实际我们没有完全理解编译期多态的意义。
正如虚函数的好处是我们可以调用一个我们并不知道的类型的成员方法一样，静态多态同样需要具备这一能力。

那么为了实现类似的行为我们应该怎么做？使用函数模板。
```cpp
template <typename D> void apply(B<D>* b, int& i) {
    b->f(++i);
}
```
可以使用任何 base class pointer 来调用这个模板函数，并且它可以自动推断 derived class 的类型。
```cpp
B<D>* b = new D;
apply(b);
```
对应运行时多态的代码：
```cpp
void apply(B* b) {...}
B* b = new D;
apply(b);
```
我们可以发现这两种代码很像。区别在于，运行时多态中，我们有一个 common base class 以及一些函数。在 CRTP 与编译期多态中，有一个 common base class template，但是没有一个 common base class，并且每一个 operates on this base template 的函数都变成了模板。

运行时多态与编译期多态的另外两个区别是纯虚函数和多态析构。
##### The compile-time pure virtual function
纯虚函数一定要被继承类所实现，否则继承类就是一个抽象类。前面实现的静态多态中没有纯虚函数的概念，比如
```cpp
// Example 02
template <typename D> class B {
public:
    ...
    void f(int i) { static_cast<D*>(this)->f(i);}
};

class D : public B<D> {
// no f() here!
};
...
B<D>* b = ...;
b->f(5); // 1
```
上述代码编译不会报错，并且调用 B::f 会导致无限循环。
```cpp
// Example 03
template <typename D> class B {
    public:
    ...
    void f(int i) { static_cast<D*>(this)->f_impl(i); }
};
class D : public B<D> {
    void f_impl(int i) { i_ += i; }
};
...
B<D>* b = ...;
b->f(5);
```
增加一个接口 f_impl 就可以实现类似纯虚函数的效果。纯虚函数和虚函数的区别是虚函数可以不被继承类实现，基类会提供一个默认实现，所以我们可以进一步模拟虚函数，通过实现一个默认版本的 B::f_impl()
```cpp
// Example 03
template <typename D> class B {
    public:
    ...
    void f(int i) { static_cast<D*>(this)->f_impl(i); }
    void f_impl(int i) {}
};
class D1 : public B<D1> {
    void f_impl(int i) { i_ += i; }
};
class D2 : public B<D2> {
    // No f() here
};

...
B<D1>* b = ...;
b->f(5); // Calls D1::f_impl()
B<D2>* b1 = ...;
b1->f(5); // Calls B::f_impl() by default个会让他6饿5分的委屈时™
```
##### Destructors and polymorphism deletion
```cpp
B<D>* b = new D;
...
delete b;
```
要求 B 的析构函数是一个虚函数，否则删除对象的时候 D 的数据成员可能无法被删除。

##### CRTP as a delegation pattern
把