#include<limits>
#include<vector>
using namespace std;

class Solution {
public:
    int best=INT_MAX;
    size_t n;
    int minimumTotal(vector<vector<int>>& triangle) {
        n=triangle.size();
        dfs(triangle,0,0,0);
        return best;
    }
    void dfs(vector<vector<int>> &triangle,int x,int y,int sum){//深度优先遍历
        if (x==n){
            best=best>sum?sum:best;
            return;
        } 
        dfs(triangle,x+1,y,sum+triangle[x][y]);
        dfs(triangle,x+1,y+1,sum+triangle[x][y]);
    }   
};

class Solution {//分治法思想的递归调用
    int height;
public:
    int minimumTotal(vector<vector<int>>& triangle) {
        height=triangle.size();
        return devideConquer(triangle,0,0);
    } 
private:
    int devideConquer(vector<vector<int>>& t,int x,int y){
        if(x==height) return 0;
        
        int left=devideConquer(t,x+1,y);
        int right=devideConquer(t,x+1,y+1);
        
        int minpath=left>=right?right:left;
        return t[x][y]+minpath;
    }
};

class Solution {//动态规划,递归版本，或者称为记忆性搜索
    int height;
    vector<vector<int>> hash;
public:
    int minimumTotal(vector<vector<int>>& triangle) {
        height=triangle.size();
        initHash(triangle);
        return devideConquer(triangle,0,0);
    } 
private:
int initHash(vector<vector<int>>& triangle)
{
    for(auto i:triangle)
        {
            vector<int> temp(i.size(),INT_MAX);
            hash.push_back(temp);
        }            
}

    int devideConquer(vector<vector<int>>& t,int x,int y){
        if(x==height)
            return 0;
        if(hash[x][y]!=INT_MAX)
            return hash[x][y];

        int left = devideConquer(t, x + 1, y);
        int right = devideConquer(t, x + 1, y + 1);
        int minpath = left >= right ? right : left;

        hash[x][y]=minpath+t[x][y];
        return hash[x][y];
    }
};

class Solution {//动态规划自底向上版本
public:
    int minimumTotal(vector<vector<int>>& triangle) {
        Init_Memo(memo,triangle);
        return Triangle_B2T_Memo(triangle,memo);
    } 
private:
    vector<vector<int>> memo;
    void Init_Memo(vector<vector<int>> &memo,const vector<vector<int>> t){
        int h=t.size()-1;
        for(int i=0;i<=h;i++){
            vector<int> temp;
            memo.push_back(temp);
            for(int j=0;j<=t[i].size()-1;j++){
                memo[i].push_back(INT_MAX);
            }
        }
        vector<int> bottom;
        memo.push_back(bottom);
        for(int i=0;i<=h+1;i++){
            memo[h+1].push_back(0);
        }
    }
    int Triangle_B2T_Memo(const vector<vector<int>> &t,vector<vector<int>> &m){
        int row = m.size()- 1;
        int col = m[row].size() - 1;
        for(--row ; row>=0; row--){
            int max_c=m[row].size() - 1;
            for(int col = 0; col <= max_c; col++){
                int min_childpath = m[row+1][col] >= m[row+1][col+1] ? m[row+1][col+1] : m[row+1][col];
                if((t[row][col] + min_childpath) < m[row][col])
                    m[row][col] = t[row][col] + min_childpath;
            }
        }
        return m[0][0];
    }
};