#include <cstdint>
#include <iostream>
#include <bitset>
#include <sys/types.h>
#include <type_traits>

template<class T>
T logicalShift(T t1, T t2) {
  return 
    static_cast<
      typename std::make_unsigned<T>::type
    >(t1) >> t2;
}

int main() {
    uint8_t x = 0b10111101;
    std::cout << static_cast<uint8_t>(x) << ' ' << std::bitset<8>(x) << ' ' << std::bitset<8>(x << 1) << std::endl;
    std::cout << x << ' ' << std::bitset<8>(x) << ' ' << std::bitset<8>(x >> 1) << std::endl;

    uint8_t x2 = 10;
    std::cout << "x2: " << static_cast<int16_t>(x2) << std::endl;

    int16_t y = 0b0000000010111101;
    std::cout << y << ' ' << static_cast<int16_t>(y) << std::endl;


    int64_t m = -1;
    std::cout << std::bitset<64>(m) << std::endl;
    std::cout << std::bitset<64>(m >> 63) << std::endl;

    m = INT64_MAX;  // 9223372036854775807
    std::cout << std::bitset<64>(m) << std::endl;
    std::cout << std::bitset<64>(m >> 63) << std::endl;

    m = 32767;
    std::cout << std::bitset<64>(m) << std::endl;
    std::cout << std::bitset<64>(m << -1) << ' ' << (m << -1) << std::endl;

    int8_t a = -1;
    std::cout << std::bitset<8>(a >> 1) << std::endl;
    std::cout << std::bitset<8>(
        static_cast<std::make_unsigned<int8_t>::type>(a) >> 1) << std::endl;
    std::cout << std::bitset<8>(
        static_cast<int8_t>(a) >> 1) << std::endl;
    std::cout << std::bitset<8>(
        static_cast<int8_t>(a) >> -1) << std::endl;


}