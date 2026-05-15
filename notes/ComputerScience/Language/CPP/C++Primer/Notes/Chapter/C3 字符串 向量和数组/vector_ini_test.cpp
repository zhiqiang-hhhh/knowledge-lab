#include <iostream>
#include <string>
#include <vector>

using namespace std;
class myclass {
 public:
  myclass() { cout << "Default Constructor\n"; }
  myclass(const myclass&) { cout << "Copy Constructor\n"; }
  myclass& operator=(myclass&) { cout << "Operator\n"; }
};

int main() {
  vector<myclass> v1(2);
  vector<int> v2(2);
  for (auto item : v2) cout << item << " ";
  cout << "=====\n";
  vector<myclass> v3(v1);
  cout << "=====\n";
  vector<myclass> v4 = v1;
}