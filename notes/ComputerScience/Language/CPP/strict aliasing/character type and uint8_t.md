
* https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1256.pdf
* https://stackoverflow.com/questions/16138237/when-is-uint8-t-%E2%89%A0-unsigned-char

理论上：

char 类型的大小并不一定是 8，C 语言标准只定义其包含 `CHAR_BIT` 个 bits。具体 `CHAR_BIT` 大小取决于编译器。

`CHAR_BIT` 定义了 width of smallest addressable units。必须在 `limits.h` 中用 constant expression 表示。

char，unsigned char 以及 signed char 都是 C 语言中的基本类型，即不论是什么编译器，都必须提供这三个类型。

uint8_t 属于 extended integer type，C 语言标准只说如果编译器提供这类那么必须满足一些规范，并没有说一定需要提供这类整数类型。

The typedef name intN_t designates a signed integer type with width N, no padding bits, and a two’s complement representation. Thus, int8_t denotes such a signed integer type with a width of exactly 8 bits.

**所以如果某个机器 CHAR_BIT > 8**，那么这个机器上的编译器不会提供 uint8_t 类型。

实际上：

1. 绝大多数机器上 `CHAT_BIT` 大小都是 8
2. 因此在绝大多数机器上，编译器都会提供 uint8_t
3. 很多编译器实现里，uint8_t 是 unsigned char 的 typedef（如果 char == unsigned char，那么 uint8_t 就是 char 的 typedef）
