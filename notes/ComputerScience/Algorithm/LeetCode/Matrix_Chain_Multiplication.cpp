#include<vector>
#include<iostream>
using namespace std;

void Init(vector<vector<unsigned int>> &m, vector<vector<unsigned int>> &s, size_t n);
void ShowMetrix(const vector<vector<unsigned int>> &m);

void Matrix_chain_order(vector<int> &q,vector<vector<unsigned int>> &m,vector<vector<unsigned int>> &s){
    auto n = q.size() - 1;
    for (decltype(n) l = 2; l <= n; l++) //l represents the len of sub-chain
        {
            for (size_t i = 1; i <= n - l + 1; i++)
            {
                size_t j = i + l - 1;
                for (size_t k = i; k <= j - 1; k++)
                {
                    unsigned int p = m[i][k] + m[k + 1][j] + q[i - 1] * q[k] * q[j];
                    if (p < m[i][j])
                    {
                        m[i][j] = p;
                        s[i][j] = k;
                    }
                }
            }
        }
}

void Init(vector<vector<unsigned int>> &m,vector<vector<unsigned int>> &s,size_t n){
    for (int i = 0; i <= n; i++)
    {
        vector<unsigned int> temp(n + 1, UINT32_MAX);
        m.push_back(temp);
    }
    for (int i = 0; i <= n - 1; i++)
    {
        vector<unsigned int> temp(n + 1, UINT32_MAX);
        s.push_back(temp);
    }

    for (int i = 0; i <= n; i++)
    {
        for (int j = 0; j <= n; j++)
        {
            if (i==j) 
            {
                m[i][j] = 0;
            }
            
        }
    }

}



unsigned int Recursice_Matrix_Chain(const vector<int> &q,vector<vector<unsigned int>> &m, int i, int j)
{
    if (m[i][j]!=UINT32_MAX) {
        return m[i][j];
    }
    if (i==j){
        m[i][j] = 0;
        return 0;
    }
    for (int k = i; k <= j - 1; k++){
        unsigned int x = Recursice_Matrix_Chain(q, m, i, k) + Recursice_Matrix_Chain(q, m, k + 1, j) + q[i - 1] * q[k] * q[j];
        if(x<m[i][j]){
            m[i][j] = x;
        }
    }
    return m[i][j];
}
int main(){
    vector<int> q{5,10,3,12,5,50,6};
    vector<vector<unsigned int>> m1, m2, s;
    Init(m1, s, q.size() - 1);
    Init(m2, s, q.size() - 1);
    Recursice_Matrix_Chain(q, m1, 1, q.size() - 1);
    Matrix_chain_order(q, m2, s);
    cout << "m1: ";
    ShowMetrix(m1);
    cout << endl;
    cout << "m2: ";
    ShowMetrix(m2);
    cout << endl;
    ShowMetrix(s);
    //cout << UINT32_MAX << endl;
    //cout << UINT16_MAX << endl;
}

void ShowMetrix(const vector<vector<unsigned int>> &m)
{
    for(auto i:m)
    {
        for(auto j:i)
        {
            if(j!=UINT32_MAX)
            {
                cout << j << ' ';
            }
        }
        cout << endl;
    }
}