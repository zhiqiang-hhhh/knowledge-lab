assign_operator 里面讨论了赋值运算符如何确保异常安全的问题。这里总结下更加广义的异常安全问题的解决方案。

异常安全的代码首先不是说不抛出异常，而是说当异常发生时，对象的状态是可被预测复合预期的，对于异常的处理可能有如下的三层处理方式：
1. 资源管理层--通常不捕获，只保证不泄漏
```cpp
// 拷贝构造函数：可能抛异常，但不需要 try-catch
CMyString(const CMyString& str) {
    m_pData = new char[strlen(str.m_pData) + 1];  // 失败就抛异常
    strcpy(m_pData, str.m_pData);
    // 如果 new 失败，对象根本没构造成功，不存在泄露问题
}

// 赋值运算符：用 copy-and-swap 保证原对象不被破坏
CMyString& operator=(CMyString str) noexcept {
    swap(m_pData, str.m_pData);  // 异常在参数构造时已经抛出
    return *this;                 // 这里永远不会抛异常
}
```
2. 业务逻辑层--选择性捕获
```cpp
void processData() {
    try {
        CMyString s1("hello");
        CMyString s2 = s1;  // new 失败会抛 std::bad_alloc
    } catch (const std::bad_alloc& e) {
        // 内存不足时的降级策略
        log("Memory allocation failed, using fallback");
        useFallbackStrategy();
    }
}
```
3. 顶层入口 —— 兜底捕获
```cpp
int main() {
    try {
        runApplication();
    } catch (const std::exception& e) {
        std::cerr << "Fatal error: " << e.what() << std::endl;
        return 1;
    }
}
```
## 核心原则

| 原则 | 说明 |
|------|------|
| **不要在构造函数里 catch 再吞掉** | 构造失败就应该让对象不存在 |
| **让异常传播到能处理它的地方** | 底层代码不知道如何恢复，上层才知道 |
| **用 RAII 保证传播过程中不泄露** | 栈展开时自动调用析构函数 |

## 实际代码中的处理位置

```cpp
// ❌ 错误：在底层吞掉异常
CMyString(const CMyString& str) {
    try {
        m_pData = new char[...];
    } catch (...) {
        m_pData = nullptr;  // 现在对象处于半死不活状态
    }
}

// ✅ 正确：让异常传播，在调用方处理
void loadConfig() {
    try {
        config_ = parseConfig(file);  // 内部可能 new 失败
    } catch (const std::bad_alloc&) {
        config_ = getDefaultConfig();  // 降级到默认配置
    }
}
```

**总结**：`new` 抛出的异常应该在**业务逻辑层**处理，而不是在资源管理类内部。资源管理类的职责是保证"要么成功，要么什么都不变"，而不是决定失败后怎么办。