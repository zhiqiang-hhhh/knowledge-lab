## 饿汉式
`Eager Initialization`

为什么叫饿汉式：生怕对象在使用的时候不存在，所以选择在一开始就把对象创建好。

```cpp
class Singleton {
    private:
        Singleton() {}
    public:
        static Singleton instance;
        static Singleton& getInstance() {
            return instance;
        }
};

Singleton Singleton::instance;
```
在某个编译单元里定义了一个静态对象，从单例模式的功能实现角度来说，这样做是可行的。但是有副作用：没有办法控制该对象的生命周期。
静态对象与全局对象的生命周期都是由编译器控制的，在程序/模块运行前创建完成，在程序退出前释放。在大多数情况下编译器控制的生命周期已经够用，但是当需要精密控制对象的生命周期时就不够用了。

## 懒汉式
`Lazy Initialization`

懒汉式：与饿汉式相反，不到使用的那一刻绝不创建对象。

```cpp
class Singleton {
public:
    static Singleton* get() {
        if (!instance) {
            instance = new Singleton();
        }
        return instance;
    }
private:
    static Singleton* instance;
};
```
按需创建。这个实现会有线程安全问题。
```cpp
class Singleton1 {
    private:
        Singleton1() {}
    public:
        static Singleton1& getInstance() {
            std::lock_guard<std::mutex> lock(mtx);
            if (instance == nullptr) {
                instance = new Singleton1();
            }
            return *instance;
        }
    private:
        static Singleton1* instance;
        static std::mutex mtx;
};

Singleton1* Singleton1::instance = nullptr;
std::mutex Singleton1::mtx;
```
引入一个静态的 mutex 解决多线程问题，但是效率较低。

改成先判断再加锁
```cpp
class Singleton2 {
    private:
        Singleton2() {}
    public:
        static Singleton2& getInstance() {
            if (instance == nullptr) {
                std::lock_guard<std::mutex> lock(mtx);
                if (instance == nullptr) {
                    instance = new Singleton2();
                }
            }
            return *instance;
        }
    private:
        static Singleton2* instance;
        static std::mutex mtx;
};

Singleton2* Singleton2::instance = nullptr;
std::mutex Singleton2::mtx;
```
## Modern Singleton
利用 C++11 起编译器保证的静态局部变量（local static）的线程安全的初始化机制。
```cpp
void func() {
    ...
    static Singleton instance;
    ...
};
```
instance 变量会在第一次执行到这条语句时被创建。
生命周期：

* 第一次执行 getInstance() 时初始化

* 整个程序运行期间都存在（直到 main 结束后析构）

* 多次调用 getInstance()，返回的始终是同一个对象

它属于 静态存储区（不是栈），但初始化时机是第一次执行到它的作用域时。

C++11 规定：函数内部的 static 局部变量在初始化时线程安全。

本质：编译器自动生成懒汉式单例。