#include <deque>
#include <iostream>
#include <list>
#include <string>
using namespace std;

void print(const std::deque<std::string>& strq) {
  for (const auto i : strq) std::cout << i << ' ';
  std::cout << std::endl;
}
void print(const std::list<std::string>& strl) {
  for (const auto i : strl) std::cout << i << ' ';
  std::cout << std::endl;
}

void in(std::istream& instream, std::deque<std::string>& targetQ) {
  std::string word;
  while (instream >> word) targetQ.push_back(word);
}

void in(std::istream& instream, list<string>& l) {
  string word;
  while (instream >> word) l.push_back(word);
}

int main() {
  std::deque<std::string> q;
  std::list<string> l;
  in(std::cin, q);
  in(cin, l);
  print(q);
  print(l);
}