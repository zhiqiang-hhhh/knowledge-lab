#include <iostream>
#include <fstream>
#include <string>
#include <stdexcept>
using namespace std;

istream& f(istream& in){
    int v;
    while(in >> v, !in.eof()){
        if(in.bad())
            throw runtime_error("IO流错误");
        if(in.fail()){
            cerr << "数据错误， 请重试： " << endl;
            in.clear();
            in.ignore(100, '\n');
            continue;
        }
    cout << v;
    }
    in.clear();
    return in;
}

istream& f2(istream& in){
    int v;
    while (in >> v)
    {
        cout << v << endl;
    }
    in.clear();
    return in;
}


int main(){
    cout << "请输入一些整数，以 Ctrl + Z 结束" << endl;
    //f2(cin);
    cout << "请输入整数： " << endl;
    char v;
    cin >> v;
    cout << v << endl;
    fstream in;
    string t;
    getline(in, t);
    return 0;
}
