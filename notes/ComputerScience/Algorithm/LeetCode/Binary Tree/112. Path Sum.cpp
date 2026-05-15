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
  bool hasPathSum(TreeNode* root, int sum) {
    // return findPathRecur(root, sum);
    return findPathIter(root, sum);
  }
  bool findPathRecur(TreeNode* root, int sum);
  bool findPathIter(TreeNode* root, int sum);
};

bool Solution::findPathRecur(TreeNode* root, int sum) {
  if (root == NULL) return false;
  if (root->val == sum && root->left == NULL && root->right == NULL) {
    return true;
  }
  return findPathRecur(root->left, sum - root->val) ||
         findPathRecur(root->right, sum - root->val);
}

bool Solution::findPathIter(TreeNode* root, int sum) {
  stack<TreeNode*> trace;
  TreeNode* last;
  int value = 0;

  while (root != NULL || !trace.empty()) {
    while (root != NULL) {
      trace.push(root);
      value += root->val;
      root = root->left;
    }

    root = trace.top();
    if (value == sum && root->left == NULL && root->right == NULL) {
      return true;
    }
    if (root->right != NULL && root->right != last) {
      root = root->right;
      // last = root;
    } else {
      trace.pop();
      value -= root->val;
      last = root;
      root = NULL;
    }
  }
  return false;
}