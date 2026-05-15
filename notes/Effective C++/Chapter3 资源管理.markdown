## Item 14 在资源管理类中小心copying行为

RAII：在对象构造期间获取资源，在对象析构期间释放资源。引出的问题：RAII管理的对象如何处理复制操作。
可能的处理方式：
1. 禁止复制。通过将 copying 操作声明为 private
2. 对被管理的资源使用引用计数。保有资源，直到其最后一个使用者被销毁。
3. 复制被管理资源：深度拷贝。
4. 转移所有权。

## Item 17 以独立语句将newed对象置入智能指针
```c++
processWidget(std::shared_ptr<Widget>(new Widget), priority());
```
这段代码有潜在的内存泄漏可能性。执行`processWidget`之前，C++编译器需要：
1. 执行 new Widget
2. 调用 shard_ptr 构造函数
3. 调用 priority()

问题在于，3与1，2的执行顺序不确定，如果执行顺序是 1 -> 3 -> 2，且 3 过程发生了异常，那么就会有内存泄漏。

更好的写法：
```c++
std::shared_ptr<Widget> pw(new Widget);
processWidget(pw, priority());
```

核心原因：编译器对于同一语句内的各项操作的执行顺序没有固定执行顺序。