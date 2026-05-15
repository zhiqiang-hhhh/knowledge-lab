基本原理
把对变长字符串的运算转换为对定长整型的等价运算。

假设有个列类型为 VARCHAR(7)，我们需要把其编码为Int64的等价整型列，之所以用 Int64 而不是 UInt64 是因为 doris 中不支持 UInt 类型的列，为了让我们的函数从接口上与 doris 统一，所以这里用 Int64，把符号位的处理交给编解码算法处理。
编码
首先，假设该字符串列包含两行：“12345”，“1234”，并且我们使用的机器为大端编码。
把字符串理解为是一个字节流，忽略其编码信息，然后把这个字符串补零补齐到 8 字节，8 字节的最低位memset成一个 UInt8，记录字符串的长度。那么从逻辑上我们应当得到如下的字节数组：
```
"12345" ==》 0x31,0x32,0x33,0x34,0x35,0x00,0x00,0x05
"1234"   ==》 0x31,0x32,0x33,0x34,0x00,0x00,0x00,0x04
```

考虑符号位为 1 的情况。
如果某个字符编码后的整型的最高位为 1，那么上述算法得到的 Int64 结果将为负数。所以需要对上述的 Int64 进行一次算数右移，并且对最高bit做一次额外的 set，来保证符号位为 0，但是在做整体的算术右移之前需要先对最低位的 size 字节左移一位做 memset，然后再整体右移，确保整体右移之后最低位的 size 值正确。
```
"12345" ==》0x18,0x99,0x19,0x9a,0x1a,0x80,0x00,0x05
"1234"   ==》0x18,0x99,0x19,0x9a,0x00,0x00,0x00,0x04
```

然后由于假设机器使用小端编码，那么实际的字节为：
```
"12345" ==》0x05,0x00,0x80,0x1a,0x9a,0x19,0x99,0x18 == 1772476078007255045
"1234"   ==》0x04,0x00,0x00,0x00,0x9a,0x19,0x99,0x18 == 1772476077562658820
```
解码
解码的时候首先读最低的size字节，然后做整体左移，再根据机器的字节序决定最终字符串的顺序。
```
"12345" ==》 0x31,0x32,0x33,0x34,0x35,0x00,0x00,0x05
"1234"   ==》 0x31,0x32,0x33,0x34,0x00,0x00,0x00,0x04
```
机器是大端法编码，那么str在 push_back的时候就需要把 int64 的高位字节push到str的开头。

Demo
```cpp
#include <bitset>
#include <cstddef>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <cstdint>
#include <stdexcept>

int64_t encodeStringToI64(const std::string& str) {
    if (str.size() > 7) {
        throw std::runtime_error("String is too long");
    }

    int64_t res = 0;
    auto ui8_ptr = reinterpret_cast<uint8_t*>(&res);

    for (size_t i = 0; i < str.size(); ++i) {
        memcpy(ui8_ptr + sizeof(res) - 1 - i, str.c_str() + i, 1);
    }

    // size 先左移一位，确保最后右移结果正确
    uint8_t size = str.size() << 1;
    // size 放在最低字节
    memset(ui8_ptr, size, 1);
    // 把符号位 set 成 0
    res &= 0x7FFFFFFFFFFFFFFF;
    return res >> 1;
}

std::string decodeStringFromI64(int64_t val) {
    auto ui8_ptr = reinterpret_cast<uint8_t*>(&val);
    // 先读 size
    int strSize = *ui8_ptr;
    
    std::string res;
    res.reserve(strSize);
    // 整体左移一位
    val = val << 1;
    // 大端表示的 int，解码得到原始 string
    for (int i = strSize - 1, j = 0; i >= 0; --i, ++j) {
        res.push_back(*(ui8_ptr + sizeof(val) - 1 - j));
    }
    return res;
}

template<typename T>
void printBytes(T val) {
    std::cout << std::endl;
    uint8_t* ui8_ptr = reinterpret_cast<uint8_t*>(&val);
    for (size_t i = 0; i < sizeof(T); ++i) {
        std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(*(ui8_ptr + i)) << '\t';
    }
    std::cout << std::dec  << std::endl;
    return;
}

int main() {
    const std::string str1 = "12345";
    const std::string str2 = "1234";

    int64_t xEncodeed1 = encodeStringToI64(str1);
    std::cout << str1 << " encodeStringToI64: " << xEncodeed1 << std::endl;
    std::cout << "decodeStringFromI64: " << decodeStringFromI64(xEncodeed1) << std::endl;
    int64_t xEncodeed2 = encodeStringToI64(str2);
    std::cout << str2 << " encodeStringToI64: " << xEncodeed2 << std::endl;
    std::cout << "decodeStringFromI64: " << decodeStringFromI64(xEncodeed2) << std::endl;

    return 0;
}
```

运行结果：
```bash
12345 encodeStringToI64: 1772476078007255045
decodeStringFromI64: 12345
1234 encodeStringToI64: 1772476077562658820
decodeStringFromI64: 1234
```
实现细节
在 be 上实现两个函数，FunctionCompressVarchar 和 FunctionDecompressVarchar
FunctionCompressVarchar 的函数入参是一个 Int8，返回值根据
