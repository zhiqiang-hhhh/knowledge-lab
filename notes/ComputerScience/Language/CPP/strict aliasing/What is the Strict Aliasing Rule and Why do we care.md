
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Understanding Strict Aliasing](#understanding-strict-aliasing)
  - [Benefits to the strict aliasing rule](#benefits-to-the-strict-aliasing-rule)
- [What is Strict Aliasing Rule and Why do we care?](#what-is-strict-aliasing-rule-and-why-do-we-care)
  - [Preliminary examples](#preliminary-examples)
  - [to the Rule-Book](#to-the-rule-book)
    - [C11 standard](#c11-standard)
  - [Are int8_t and uint8_t char types?](#are-int8_t-and-uint8_t-char-types)
  - [What is Type Punning](#what-is-type-punning)
  - [How do we Type Pun correctly?](#how-do-we-type-pun-correctly)

<!-- /code_chunk_output -->



# Understanding Strict Aliasing

    https://cellperformance.beyond3d.com/articles/2006/06/understanding-strict-aliasing.html

One pointer is said to alias another pointer when both refer to the same location or object.

```c
uint32_t
swap_words(uint32_t arg)
{
    uint16_t* const sp = (uint16_t*)&arg;
    uint16_t hi = sp[0];
    uint16_t lo = sp[1];

    sp[1] = hi;
    sp[0] = lo;

    return (arg);
}
```
sp 指向的内存地址是 &arg 的别名（alias），因为他们在内存中是同一个地址。在 C99 中，两个不同类型的指针互为别名是非法操作。This is often refered to as the strict aliasing rule. 当使用 GCC -O2 时改规则默认启用。此时，尽管上述代码可以正常编译，但是实际上的运行结果可能是 UB。一种非常可能的情况是，汇编代码会直接返回 arg 的内容，因为在 strict alias 规则下，编译器认为 uint16_t* 不会改变 uint32_t 指向的内容，所以编译器可以理直气壮返回原始值。


## Benefits to the strict aliasing rule
**When the compiler cannot assume that two object are not aliased, it must act very conservatively when accessing memory.**

```c
uint32_t
swap_words(uint32_t arg)
{
    char* const cp = (char*)&arg;
    const char c0 = cp[0];
    const char c1 = cp[1];
    const char c2 = cp[2];
    const char c3 = cp[3];

    cp[0] = c2;
    cp[1] = c3;
    cp[2] = c0;
    cp[3] = c1;
    
    return (arg);
}
```

# What is Strict Aliasing Rule and Why do we care?

## Preliminary examples
```cpp
int x = 10;
int *ip = &x; // valid pointer alias
    
std::cout << *ip << "\n";
*ip = 12;
std::cout << x << "\n";
```
```cpp
int foo( float *f, int *i ) { 
    *i = 1;               
    *f = 0.f;            
   
   return *i;
}

int main() {
    int x = 0;
    
    std::cout << x << "\n";   // Expect 0
    x = foo(reinterpret_cast<float*>(&x), &x);  // invalid pointer alias
    std::cout << x << "\n";   // Expect 0?
}
```

## to the Rule-Book
### C11 standard
An object shall have its stored value accessed only by an lvalue expression that has one of the following types:
- a type compatible with the effective type of the object
```cpp
int x = 1;
int *p = &x;
```
- a qualified version of a type compatible with the effective type of the object
```cpp
int x = 1;
const int* p = &x;
```
- a type that is signed or unsigned type corresponding to the effective type of the objec
```cpp
int x = 1;
unsigned int *p = (unsigned int*)&x;
```
- a type that is the signed or unsigned type corresponding to a qualified version of the effective type of the object
```cpp
int x = 1;
const unsigned int *p = (const unsigned int*)&x;
```
- an aggregate or union type that includes one of the aforementioned types among its members(including, recusively, a member of a subaggregate or contained union)
```cpp
struct foo {
    int x;
};

void foobar(struct foo *fp, int *ip);

foo f;
foobar(&f, &f.x);
```
- or a character type
```cpp
int x = 65;
char *p = (char *)&x;
```
- a type that is a (possibly cv-qualified) base class type of the dynamic type of the object
```cpp
struct foo {int x;};
struct bar : public foo {};

int foobar( foo &f, bar &b) {
    f.x = 1;
    b.x = 2;

    returnm f.x;
}
```
- a char, unsigned char, or std::byte type
```cpp
int foo( std::byte &b, uint32_t &ui ) {
    b = static_cast<std::byte>('a');
    ui = 0xFFFFFFFF;

    return std::to_integer<int>(b);
}
```

**注意 signed char 不在上述列表里，这是 C 与 C++ 的一个重要区别，C 中说的是 char type。**

## Are int8_t and uint8_t char types?
**Theoretically neither int8_t nor uint8_t have to be char types but practically they are implemented that way.**

因此错用 uint8 或者 int8 可能会导致严重的性能问题！

https://stackoverflow.com/questions/26295216/using-this-pointer-causes-strange-deoptimization-in-hot-loop

## What is Type Punning
## How do we Type Pun correctly?
The standard blessed method for type punning in both C and C++ is **memcpy**. This may seem a little heavy handed but the optimizer should recognize the use of memcpy for type punning and optimize it away and generate a register to register move.

https://gcc.godbolt.org/z/zWrEvPMGo

## Type Punning Arrays
```cpp
// Simple operation just return the value back
int foo( unsigned int x ) { return x ; }

// Assume len is a multiple of sizeof(unsigned int) 
int bar( unsigned char *p, size_t len ) {
  int result = 0;

  for( size_t index = 0; index < len; index += sizeof(unsigned int) ) {
    unsigned int ui = 0;                                 
    std::memcpy( &ui, &p[index], sizeof(unsigned int) );

    result += foo( ui ) ;
  }

  return result;
}
```