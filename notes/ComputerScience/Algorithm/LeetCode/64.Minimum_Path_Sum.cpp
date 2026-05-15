#include<vector>
#include<algorithm>
using namespace std;

class Solution {
public:
    int minPathSum(vector<vector<int>>& grid) {
        int rows = grid.size();
        int cols = grid[0].size();
        
        if(rows==0 || cols==0)
            return 0;
        
        vector<vector<int>> memo ;
        initMemo(memo, rows, cols);
        
        return DP_minPathSum(memo, grid, rows, cols);
        
    }
    
    void initMemo(vector<vector<int>> &memo, int rows, int cols){
        for(int i=0; i<rows; i++){
            
            vector<int> temp;
            
            for(int j=0; j<cols; j++){
                if(i==0 || j==0)
                    temp.push_back(0);
                else
                    temp.push_back(INT_MAX);
            }
            memo.push_back(temp);
        }
    }
    
    int DP_minPathSum(vector<vector<int>> &memo, const vector<vector<int>> &grid, int row, int col){
        memo[0][0] = grid[0][0];
        
        for(int i=1; i<row; i++)
            memo[i][0] = memo[i-1][0] + grid[i][0];
        for(int j=1; j<col; j++)
            memo[0][j] = memo[0][j-1] + grid[0][j];
        
        for(int i=1; i<row; i++){
            for(int j=1; j<col; j++)
                memo[i][j] = min(memo[i-1][j] , memo[i][j-1]) + grid[i][j];
        }
        
        return memo[row-1][col-1];
    }
};