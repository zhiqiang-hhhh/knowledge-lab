#include <iostream>
#include <stdexcept>
using namespace std;

istream& f(istream & in)
{
    int v;
    while(in >> v, !in.eof()){
        if(in.bad())
            throw runtime_error("IO留错误");
            
        if(in.fail()){
            cerr << "数据错误，请重试： " << endl;
        }
    }
}