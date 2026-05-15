#include<iostream>
#include<vector>
#include<string>
#include<math.h>
using namespace std;

int best = INT_MAX;
/*
void DFS(vector<vector<int>> t,int x,int y,int sum){
    if(x == t.size()){
        best = best > sum ? sum : best;
        return;
        }
    DFS(t, x + 1, y,sum+t[x][y]);
    DFS(t, x + 1, y + 1, sum + t[x][y]);
}
//    return;
int minimumTotal(vector<vector<int>> t){
    DFS(t, 0, 0, 0);
    return best;
}*/
void DFS(vector<vector<int>> t,int x,int y,int sum){
    sum += t[x][y];
    if(x+1 == t.size()){
        best = best > sum ? sum : best;
        return;
        }
    for (int i = 0; i < t[x + 1].size(); i++)
        {
            cout << t[x][y] << endl;
            DFS(t, x + 1, i, sum);
        }
}
    
   // DFS(t, x + 1, y,sum+t[x][y]);
   // DFS(t, x + 1, y + 1, sum + t[x][y]);
//    return;
int minimumTotal(vector<vector<int>> t){
    DFS(t, 0, 0, 0);
    return best;
    }
int main(){
    vector<vector<int>> trainangle = {{2}, {3, 4}, {6, 5, 7}, {4, 3, 8, 1}};
    //DFS(trainangle, 0, 0);
    //cout << minimumTotal(trainangle);

    vector<vector<int>> hash;
    int n = 0;
    
    for(auto i:trainangle)
    {
        for(auto j:i)
        {
            hash[n].push_back(j);
        }
        n++;
    }
    for(auto i:hash)
    {
        for(auto j:i)
        {
            cout << j << ' ';
        }
        cout << endl;
    }

}

