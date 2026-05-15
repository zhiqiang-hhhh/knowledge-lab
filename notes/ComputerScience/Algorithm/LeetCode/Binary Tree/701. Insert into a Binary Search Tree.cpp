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
  TreeNode* insertIntoBST(TreeNode* root, int val) {
    TreeNode* y = nullptr;
    TreeNode* x = root;
    while (x != nullptr) {
      y = x;
      if (x->val < val)
        x = x->right;
      else
        x = x->left;
    }
    TreeNode* z = new TreeNode(val);
    if (y != nullptr && y->val <= val)
      y->right = z;
    else
      y->left = z;
    return root;
  }
};