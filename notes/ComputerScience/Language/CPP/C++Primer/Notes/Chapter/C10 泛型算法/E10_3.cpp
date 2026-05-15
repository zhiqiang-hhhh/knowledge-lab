#include <algorithm>
#include <fstream>
#include <iostream>
#include <list>
#include <numeric>
#include <string>
#include <vector>
using namespace std;

int main(int argc, char *argv[]) {
  ifstream in(argv[1]);
  if (!in) {
    cout << "输入文件打开失败。" << endl;
    exit(1);
  }

  vector<int> v;
  int val;
  while (in >> val) {
    v.push_back(val);
  }

  cout << accumulate(v.begin(), v.end(), 0) << endl;
}
