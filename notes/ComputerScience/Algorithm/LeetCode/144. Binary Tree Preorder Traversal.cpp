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
  vector<int> preorderTraversal(TreeNode* root) {
    vector<int> res;
    stack<TreeNode*> trace;

    if(root != NULL){
        trace.push(root);
    }
    while(!trace.empty()){
        TreeNode* temp = trace.top();
        res.push_back(temp->val);
        trace.pop();
        if(temp->right != NULL)
            trace.push(temp->right);
        if(temp->left != NULL)
            trace.push(temp->left);
    }
    return res;
  }
};