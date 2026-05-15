---
layout: post
title:  "[C++] C++ Exception 性能测试与实现浅探"
date:   2021-07-03 19:28:11 +0800
categories: jekyll update
---

# C++ Exception 性能测试与实现浅探
[TOC]
很多编程语言中都有 Exception 机制。利用 Exception 机制，一段代码可以绕过正常的代码执行路径去通知另一段代码，有一些意外事件或者错误情况发生。另一种常见的异常/错误处理机制是 ErrorCode，熟悉 C 语言的同学应该体会很深，比如操作系统提供的接口很多都是以 ErrorCode 的形式判断是否发生异常。

C++ 并不像 Java 一样强制程序员使用 Exception，但是在 C++ 中处理 Exception 是不可避免的，比如当内存不足时，new 操作符会抛出`std::bad_alloc`。同时在 C++ 中单纯使用 ErrorCode 来标记异常情况也有其他问题：
1. ErrorCode 没有统一标准，没有严格标准规定到底是返回使用 -1 表示 Error 还是使用 0 表示 Error，所以你需要额外配合使用枚举；
2. ErrorCode 可能会被忽略，虽然 C++17 中有了`[[nodiscard]]`属性，但是你还是有可能会忘记加 nodiscard！毕竟忘记加 nodiscard 并不比忘记处理 ErrorCode 难多少。。

因此，掌握 C++ Exception 的原理以及正确使用方式是非常必要的。同时 C++ 目前依然是在高性能编程场景下的首选编程序言，很多同学出于性能考虑不敢使用 C++ Exception，只知道 Exception 慢，但是并不知道到底是为什么慢，究竟慢在哪里。

本文的目的是对 C++ Exception 进行简单测试与分析。首先对 Exception 的性能进行评测，探究 C++ Exception 对程序性能的影响，然后对 C++ Exception 的实现机制做一个简单探索，让大家明白 Exception 对程序运行到底产生了哪些影响，进而写出更高质量的代码。

## Benchmark

首先我们先通过性能测试直观地感受一下添加 Exception 对程序性能的影响。

参考[Investigating the Performance Overhead of C++ Exceptions](https://pspdfkit.com/blog/2020/performance-overhead-of-exceptions-in-cpp/)的测试思路，我们对其测试用例进行改动。简单解释一下我们的测试代码：
我们定义一个函数，该函数会根据概率决定是否调用目标函数：
```c++
const int randomRange = 2;
const int errorInt = 1;
int getRandom() { return random() % randomRange; }

template<typename T>
T testFunction(const std::function<T()>& fn) {
    auto num = getRandom();
    for (int i{0}; i < 5; ++i) {
        if (num == errorInt) {
            return fn();
        }
    }
}
```
执行 testFunction 时，目标函数 fn 有 50% 的概率被调用。

```c++
void exitWithStdException() {
    testFunction<void>([]() -> void {
        throw std::runtime_error("Exception!");
    });
}

void BM_exitWithStdException(benchmark::State& state) {
    for (auto _ : state) {
        try {
            exitWithStdException();
        } catch (const std::runtime_error &ex) {
            BLACKHOLE(ex);
        }
    }
}
```
BM_exitWithStdException 用于测试函数 exitWithStdException，该函数会抛出一个 Exception，然后在 BM_exitWithStdException 中立刻被 catch，catch 后我们什么也不做。

类似的，我们设计用于测试 ErrorCode 模式的代码如下：
```c++
void BM_exitWithErrorCode(benchmark::State& state) {
    for (auto _ : state) {
        auto err = exitWithErrorCode();
        if (err < 0) {
            // handle_error()
            BLACKHOLE(err);
        }
    }
}

int exitWithErrorCode() {
    testFunction<int>([]() -> int {
        return -1;
    });

    return 0;
}
```
将 ErrorCode 测试代码放进 try{...}catch{...} 测试只进入 try 是否会对性能有影响：
```c++
void BM_exitWithErrorCodeWithinTry(benchmark::State& state) {
    for (auto _ : state) {
        try {
            auto err = exitWithErrorCode();
            if (err < 0) {
                BLACKHOLE(err);
            }
        } catch(...) {
        }
    }
}
```

利用 gtest/banchmark 开始我们的测试：
```c++
BENCHMARK(BM_exitWithStdException);
BENCHMARK(BM_exitWithErrorCode);
BENCHMARK(BM_exitWithErrorCodeWithinTry);

BENCHMARK_MAIN();
```
测试结果：
```bash
2021-07-08 20:59:44
Running ./benchmarkTests/benchmarkTests
Run on (12 X 2600 MHz CPU s)
CPU Caches:
  L1 Data 32K (x6)
  L1 Instruction 32K (x6)
  L2 Unified 262K (x6)
  L3 Unified 12582K (x1)
Load Average: 2.06, 1.88, 1.94
***WARNING*** Library was built as DEBUG. Timings may be affected.
------------------------------------------------------------------------
Benchmark                              Time             CPU   Iterations
------------------------------------------------------------------------
BM_exitWithStdException             1449 ns         1447 ns       470424
BM_exitWithErrorCode                 126 ns          126 ns      5536967
BM_exitWithErrorCodeWithinTry        126 ns          126 ns      5589001
```
这是我在自己的 mac 上测试的结果，使用的编译器版本为`gcc version 10.2.0`，异常模型为`DWARF2`。可以看到，当 Error/Exception 发生率为 50% 时，Exception 的处理速度要比返回 ErrorCode 慢 10 多倍。同时，对一段不会抛出异常的代码添加 try{...}catch{...} 则不会对性能有影响。我们可以再将 Error/Exception 的发生率调的更低测试下：
```c++
const int randomRange = 100;
const int errorInt = 1;
int getRandom() { return random() % randomRange; }
```
我们将异常的概率降低到了 1%，继续测试：
```bash
2021-07-08 21:16:01
Running ./benchmarkTests/benchmarkTests
Run on (12 X 2600 MHz CPU s)
CPU Caches:
  L1 Data 32K (x6)
  L1 Instruction 32K (x6)
  L2 Unified 262K (x6)
  L3 Unified 12582K (x1)
Load Average: 2.80, 2.22, 1.93
***WARNING*** Library was built as DEBUG. Timings may be affected.
------------------------------------------------------------------------
Benchmark                              Time             CPU   Iterations
------------------------------------------------------------------------
BM_exitWithStdException              140 ns          140 ns      4717998
BM_exitWithErrorCode                 111 ns          111 ns      6209692
BM_exitWithErrorCodeWithinTry        113 ns          113 ns      6230807
```
可以看到，Exception 模式的性能大幅提高，接近了 ErrorCode 模式。

从实验结果，我们可以得出如下的结论：

1. 在 throw 发生的很频繁的情况（50%）下，Exception 机制相比 ErrorCode 会慢非常多;
2. 在 throw 并不是经常发生的情况（1%）下，Exception 机制并不会比 ErrorCode 慢；

由此结论，我们可以进而得到如下的使用建议：

- 不要使用 try{throw ...}catch(){...} 来充当你的代码控制流，这会导致你的 C++ 慢的离谱
- 应当把 Exception 用在真正发生异常的情况下，比如内存超限、数据格式错误等较为严重却不会经常发生的场景下

## libc++ Exception 实现浅探

前一节我们验证了 C++ Exception 在频繁发生异常的情况下会导致程序性能变慢的现象，这一节开始我们尝试去寻找导致这一现象的原因。

首先，Exception 机制的实现位于 C++ 标准库中，而由于 C 语言中没有 Exception 机制，我们可以尝试将具有 throw 关键字的由 .cpp 编译而来的可重定位二进制文件与由 .c 编译得到的包含 main 函数的二进制进行链接。目的是找出对于 throw 关键字，libc++ 为我们最终生成的可执行文件添加了哪些额外函数。

throw.h:
```c++
/// throw.h
struct Exception {};

#ifdef __cplusplus
extern "C" {
#endif

    void raiseException();

#ifdef __cplusplus
};
#endif
```
throw.cpp
```c++
/// throw.cpp
#include "throw.h"

extern "C" {
    void raiseException() {
        throw Exception();
    }
}
```
raiseException 函数只是简单的抛出异常。这里我们使用 `extern "C"` 告诉 C++ 编译器，按照 C 语言的规则去生成临时函数名，目的是为了让生成的可重定位目标文件能够被后续用 C 语言完成的 main 函数链接。main.c 如下：

```c
/// main.c
#include "throw.h"

int main() {
    raiseException();
    return 0;
}
```
我们分别编译 throw.cpp 和 main.c：
```bash
> g++ -c -o throw.o -O0 -ggdb throw.cpp
> gcc -c -o main.o -O0 -ggdb main.c
```
直觉来说，我们是可以完成链接的，毕竟函数 raiseException 的定义是完整的。试验一下：
```bash
> gcc main.o throw.o -o app

Undefined symbols for architecture x86_64:
  "__ZTVN10__cxxabiv117__class_type_infoE", referenced from:
      __ZTI9Exception in throw.o
  NOTE: a missing vtable usually means the first non-inline virtual member function has no definition.
  "___cxa_allocate_exception", referenced from:
      _raiseException in throw.o
  "___cxa_throw", referenced from:
      _raiseException in throw.o
ld: symbol(s) not found for architecture x86_64
collect2: error: ld returned 1 exit status
```
链接出错了，报错信息看上去好像懂了——应该跟 Exception 相关，但是很明显我们并没有完全懂——这三个未定义的符号到底是啥？

这三个符号：__ZTVN10__cxxabiv117__class_type_infoE, ___cxa_allocate_exception, ___cxa_throw，均代表了 libc++ 中对应 Exception 处理机制的入口函数。是编译器在编译时添加的部分，链接时的会在 libc++ 中寻找这三个符号的完整定义。
我们链接时使用的是 gcc 指令，只会链接 libc，C 语言中并没有这三个符号的定义，所以我们在链接时才会报错。改用 g++ 链接之后确实没问题了：
```bash
> g++ main.o throw.o -o app                   
> ./app
terminate called after throwing an instance of 'Exception'
[1]    37016 abort      ./app
```

通过这个 demo 我们知道，g++ 确实在编译与链接时做了一些额外的工作，帮我们实现了 throw 关键字。对于`try {...} catch () {...}`来说也一样，链接时会链接到 libc++ 中对应的函数实现，我们通过汇编代码再来体会一下：
```c++
...
void raise() {
    throw Exception();
}

void try_but_dont_catch() {
    try {
        raise();
    } catch(Fake_Exception&) {
        printf("Running try_but_dont_catch::catch(Fake_Exception)\n");
    }

    printf("try_but_dont_catch handled an exception and resumed execution");
}
...
```
对应的汇编（精简过后）：
```asm
...
_Z5raisev:
    call    __cxa_allocate_exception
    call    __cxa_throw

_Z18try_but_dont_catchv:
    .cfi_startproc
    .cfi_personality 0,__gxx_personality_v0
    .cfi_lsda 0,.LLSDA1
    ...
    call    _Z5raisev
    jmp     .L8
    ...
```
_Z5raisev 对应函数 raise 函数的实现，从字面意思就可以看出`__cxa_allocate_exception`是为 Exception 类型分配空间，`__cxa_throw`函数的实现位于 libc++ 中，该函数是后续 Exception 处理机制的入口。z18try_but_dont_catchv 的的前三行先不管，直接看到 call _Z5raisev。到这里也很好理解，如果 _Z5raisev 执行正常的话，跳到 .L8 程序正常退出。
```asm
.L8:
    leave
    .cfi_restore 5
    .cfi_def_cfa 4, 4
    ret
    .cfi_endproc
```
如果 try 内的代码执行出现问题，那么会执行这段代码（怎么跳过来的我们目前还不知道）：
```asm
    cmpl    $1, %edx
    je      .L5

.LEHB1:
    call    _Unwind_Resume
.LEHE1:

.L5:
    call    __cxa_begin_catch
    call    __cxa_end_catch
```
这段汇编，首先比较 Exception 的类型，如果能够类型匹配，就去执行 .L5，如果不匹配，我们就会顺序执行到 _Unwind_Resume。
很明显，.L5 的部分对应代码的 catch 关键字，而且 .L5 执行之后也会跳到 .L8，该函数可以正常退出。

Unwind_Resume 应该又是 libc++ 里面的函数了。该函数的作用是去其他栈帧寻找是否有该类型 Exception 的处理函数。

看到这里，其实我们就能够明白了导致之前测试结果的原因：
1. try 后面若不抛出异常，则程序的执行流程不会执行 `__cax_throw`
2. `__cax_throw`是后续的异常判断以及栈回退的入口，不执行该函数则不会对性能有影响
3. `__cax_throw`执行后，会逐个栈帧寻找异常处理函数，该过程会导致严重的性能损耗

## 总结

本文简单地对 C++ Exception 的性能做了一个测试，由测试结果我们进行了合理的推测：C++ Exception 背后处理的过程是由 libc++ 中对应的函数实现的，并且对该推测进行了验证。
实际上 C++ Exception 的完整实现还有很多深入的细节，感兴趣的同学可以进一步探索。

## 参考文献
- https://monkeywritescode.blogspot.com/search?q=C%2B%2B+exception
- https://pspdfkit.com/blog/2020/performance-overhead-of-exceptions-in-cpp/