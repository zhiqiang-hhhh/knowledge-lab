#include <iostream>
#include <string.h>

class CMyString3 {
public:
  CMyString3(char *pData = nullptr) {
    if (pData) {
      m_pData = new char[strlen(pData) + 1];
      strcpy(m_pData, pData);
    } else {
      m_pData = new char[1];
      m_pData[0] = '\0';
    }
  }

  CMyString3(const CMyString3 &str) {
    std::cout << "Copy constructor called" << std::endl;
    m_pData = new char[strlen(str.m_pData) + 1];
    strcpy(m_pData, str.m_pData);
  }

  CMyString3(CMyString3 &&str) noexcept {
    std::cout << "Move constructor called" << std::endl;
    m_pData = str.m_pData;
    str.m_pData = nullptr;
  }

  CMyString3 &operator=(const CMyString3& str) {
    std::cout << "Copy assignment operator called." << std::endl;
    CMyString3 temp(str);
    std::swap(temp.m_pData, this->m_pData);
    return *this;
  }

  CMyString3 &operator=(CMyString3&& str) noexcept {
    std::cout << "Move assignment operator called" << std::endl;
    std::swap(m_pData, str.m_pData);
    return *this;
  }

  ~CMyString3() { delete[] m_pData; }

private:
  char *m_pData;
};


class CMyString4 {
public:
  CMyString4(char *pData = nullptr) {
    if (pData) {
      m_pData = new char[strlen(pData) + 1];
      strcpy(m_pData, pData);
    } else {
      m_pData = new char[1];
      m_pData[0] = '\0';
    }
  }

  CMyString4(const CMyString4 &str) {
    std::cout << "Copy constructor called" << std::endl;
    m_pData = new char[strlen(str.m_pData) + 1];
    strcpy(m_pData, str.m_pData);
  }

  CMyString4(CMyString4 &&str) noexcept {
    std::cout << "Move constructor called" << std::endl;
    m_pData = str.m_pData;
    str.m_pData = nullptr;
  }

  CMyString4 &operator=(CMyString4 str) noexcept {
    std::cout << "Move assignment operator called" << std::endl;
    std::swap(m_pData, str.m_pData);
    return *this;
  }

  ~CMyString4() { delete[] m_pData; }

private:
  char *m_pData;
};

int main() {
  CMyString4 str1("Hello");
  CMyString4 str2("World");
  std::cout << "Before move" << std::endl;
  str2 = str1;
  std::cout << "Do move" << std::endl;
  str2 = std::move(str1);
  return 0;
}