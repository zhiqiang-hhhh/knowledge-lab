#include<iostream>
#include<string>
using namespace std;

class NoDefault
{
    public:
    NoDefault(int i){
        val = i;
    }
    int val;
};

class C
{
public:
    NoDefault nd;
    C(int i = 0): nd(i) {}
};