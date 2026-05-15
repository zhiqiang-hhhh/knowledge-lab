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
  vector<int> inorderTraversal(TreeNode* root) {
    vector<int> res;
    stack<TreeNode*> trace;

    while(root != NULL || !trace.empty()){
        while(root != NULL){
            trace.push(root);
            root = root->left;
        }
        TreeNode* temp = trace.top();
        trace.pop();
        res.push_back(temp->val);
        root = temp->right;
    }
    return res;
  }
};

