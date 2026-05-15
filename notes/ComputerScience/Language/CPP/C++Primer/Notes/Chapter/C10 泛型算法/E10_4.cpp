#include <fstream>
#include <iostream>
#include <numeric>
#include <vector>
using namespace std;

int main(int argc, char* argv[]) {
  ifstream in(argv[1]);
  if (!in) {
    cout << "Open File ERROR\n";
    return 0;
  }

  vector<double> vd;
  double val;
  while (in >> val) {
    vd.push_back(val);
  }

  cout << accumulate(vd.begin(), vd.end(), 0.0) << endl;
}