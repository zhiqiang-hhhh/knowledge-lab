#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
using namespace std;

void elimDups(vector<string> &);
void printWords(vector<string> &w) {
  for (auto i = w.begin(); i != w.end(); i++) {
    cout << *i << ' ';
  }
  cout << endl;
}
int main() {
  vector<string> vs;
  string val;
  while (cin >> val) {
    vs.push_back(val);
  }
  elimDups(vs);
}
void elimDups(vector<string> &word) {
  printWords(word);
  sort(word.begin(), word.end());
  auto end_unique = unique(word.begin(), word.end());
  word.erase(end_unique, word.end());
  printWords(word);
}