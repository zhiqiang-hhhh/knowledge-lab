/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */
class Solution {
public:
    int maxPathSum(TreeNode* root){
        int _sum = INT32_MIN;
        helper(root, _sum);
        return _sum;
    }
    int helper(TreeNode* root, int& _sum) {
        if(root == NULL) return 0;
        
        int sumL = helper(root->left, _sum);
        int sumR = helper(root->right, _sum);
        
        sumL = sumL > 0 ? sumL : 0;
        sumR = sumR > 0 ? sumR : 0;
        int sumNow = sumL + sumR + root->val;
        _sum = max(_sum, sumNow);
        
        return root->val + max(sumL, sumR);
    }

};