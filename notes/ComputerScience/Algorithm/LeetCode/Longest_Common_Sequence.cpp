#include<string>
#include<vector>
#include<iostream>
#include<queue>
#include<algorithm>
using namespace std;
int LCS(const string &s1, const string &s2, vector<vector<int>> &c, int i, int j){
    if(i == -1 || j == -1)
        return 0;
    if(c[i][j] != INT_MAX)
        return c[i][j];
    if(s1[i] == s2[j])
        c[i][j] = LCS(s1, s2, c, i - 1, j - 1) + 1;
    else{
        int t1 = LCS(s1, s2, c, i, j - 1);
        int t2 = LCS(s1, s2, c, i - 1, j);
        c[i][j] = (t1 >= t2 ? t1 : t2);
    }
    return c[i][j];
}
void Init_C(const string &s1, const string &s2, vector<vector<int>> &c){
    int l1 = s1.size() - 1;
    int l2 = s2.size() - 1;
    for (int i = 0; i <= l1; i++){
        vector<int> temp;
        for (int j = 0; j <= l2; j++){
                temp.push_back(INT_MAX);
        }
        c.push_back(temp);
    }
}

void ShowMetrix(const vector<vector<int>> &m){
    for(auto i:m)
    {
        for(auto j:i)
        {
            //if(j!=UINT32_MAX)
            //{
                cout << j << ' ';
            //}
        }
        cout << endl;
    }
}

int main(){
    string s1 = "ACCGGTCGAGTGCGCGGAAGCCGGCCGAA";
    string s2 = "GTCGTTCGGAATGCCGTTGCTCTGTAAA";
    //string s1 = "abcbdab";
    //string s2 = "bdcaba";
    cout << "sizeof s1: " << s1.size() << endl;
    cout << "sizeof s2: " << s2.size() << endl;

    vector<vector<int>> c;
    Init_C(s1, s2, c);
   // ShowMetrix(c);
    //string LCSr = LCS(s1, s2);
    //cout << LCSr << endl;
    string ans = "GTCGTCGGAAGCCGGCCGAA";
    //string ans = "12312";
    cout << "ANS: " << ans.size() << endl;
    cout << "LCS: " << LCS(s1, s2, c, s1.size() - 1, s2.size() - 1) << endl;
    //ShowMetrix(c);
}