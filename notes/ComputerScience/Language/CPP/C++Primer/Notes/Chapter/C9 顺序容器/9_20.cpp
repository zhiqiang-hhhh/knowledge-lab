#include <string>
#include <list>
#include <deque>
#include <iostream>
using namespace std;

int main(){
    list<int> il;
    deque<int> odd;
    deque<int> even;
    for(const auto i: il)
    {
        if(i % 2) odd.push_back(i);
        else even.push_back(i);
    }
}