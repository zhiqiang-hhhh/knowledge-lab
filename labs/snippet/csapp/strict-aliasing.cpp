#include <bitset>
#include <cstdint>
#include <cstdio>
#include <iostream>

template<typename T>
std::string to_hex(T v) {
    const static uint8_t H0 = 0x0;
    const static uint8_t H1 = 0x1;
    const static uint8_t H2 = 0x2;
    const static uint8_t H3 = 0x3;
    const static uint8_t H4 = 0x4;
    const static uint8_t H5 = 0x5;
    const static uint8_t H6 = 0x6;
    const static uint8_t H7 = 0x7;
    const static uint8_t H8 = 0x8;
    const static uint8_t H9 = 0x9;
    const static uint8_t HA = 0xA;
    const static uint8_t HB = 0xB;
    const static uint8_t HC = 0xC;
    const static uint8_t HD = 0xD;
    const static uint8_t HE = 0xE;
    const static uint8_t HF = 0xF;

    const size_t constexpr hex_count = sizeof(T) * 2;
    char res[sizeof(T) * 2];
    
    for(size_t i = 0; i < sizeof(T) * 2; ++i) {
        size_t idx =  hex_count - 1 - i;
        uint8_t tmp = v >> (i * 4);
        switch (tmp & HF) {
            case H0:
                res[idx] = '0';
                break;
            case H1:
                res[idx] = '1';
                break;
            case H2:
                res[idx] = '2';
                break;
            case H3:
                res[idx] = '3';
                break;
            case H4:
                res[idx] = '4';
                break;
            case H5:
                res[idx] = '5';
                break;
            case H6:
                res[idx] = '6';
                break;
            case H7:
                res[idx] = '7';
                break;
            case H8:
                res[idx] = '8';
                break;
            case H9:
                res[idx] = '9';
                break;
            case HA:
                res[idx] = 'A';
                break;
            case HB:
                res[idx] = 'B';
                break;
            case HC:
                res[idx] = 'C';
                break;
            case HD:
                res[idx] = 'D';
                break;
            case HE:
                res[idx] = 'E';
                break;
            case HF:
                res[idx] = 'F';
                break;
        }
    }

    return std::string(res);
}

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

int main () {
    uint32_t x = 0xFFFF1111;
    std::cout << to_hex(x) << std::endl;
    uint32_t sw_x = swap_words(x);
    std::cout << to_hex(sw_x) << std::endl;
}