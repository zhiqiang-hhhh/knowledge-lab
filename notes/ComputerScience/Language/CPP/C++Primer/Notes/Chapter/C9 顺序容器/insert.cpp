#include <forward_list>
#include <iostream>
#include <list>
#include <vector>
using namespace std;

int main() {
  vector<int> ivec{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
  vector<int>::iterator iter = ivec.begin();
  cout << *iter << endl;
  iter = ivec.insert(ivec.end(), 11);
  cout << *iter << endl;
  //
  iter = ivec.insert(ivec.begin(), 0);
  cout << *iter << endl;

  iter = ivec.begin();
  vector<int>::iterator mid = iter + ivec.size() / 2;
  while (iter != mid) {
    if ((*iter) % 2) *iter = 2 * (*iter);
    iter++;
  }
  for (auto i : ivec) cout << i << ' ';
  cout << endl;
  forward_list<int> flst;
}