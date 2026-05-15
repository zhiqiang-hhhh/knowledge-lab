# 实现
## Item26 延后变量定义式的出现时间
加入某个变量被初始化之后，却因为其他原因（函数提前返回、抛出异常）未被使用，那么就会白白承担函数的初始化成本。

默认构造函数能跳过则跳过。

## Item27 尽量少做转型动作

* const_cast
* dynamic_cast: 把 pointer to base class 转为 pointer to derived class。**唯一可能导致重大运行成本的转型**
* reinterpret_cast: 
* static_cast: 

## Item28 避免返回 handless 指向对象内部成分
handless：指针、引用、迭代器，对象内部成分：private

如果返回 private 的 handless，相当于其变为 public，一定程度上违反了封装特性，而且也带来悬空 handless 的风险。

有时这种操作是无法避免的，但是我们应当尽量避免此类操作。

## Item29 努力实现异常安全
异常安全：
* 不泄漏任何资源：互斥锁、heap memory 等
* 不允许数据败坏：发生异常后，没有任何对象获得不必要的修改

第一条较为容易实现，第二条就比较难了。