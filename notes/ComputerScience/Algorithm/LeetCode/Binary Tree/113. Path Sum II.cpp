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
  vector<vector<int>> pathSum(TreeNode* root, int sum) {
    vector<vector<int>> res;
    // vector<int> path;
    findPathDFS(root, sum, res);
    return res;
  }

 private:
  void findPathRecursion(TreeNode* root, int sum, vector<int> path,
                         vector<vector<int>>& res);
  void findPathDFS(TreeNode* root, int sum, vector<vector<int>>& res);
};

void Solution::findPathRecursion(TreeNode* root, int sum, vector<int> path,
                                 vector<vector<int>>& res) {
  if (root == NULL) {
    return;
  }
  if (root->val == sum && root->left == NULL && root->right == NULL) {
    path.push_back(root->val);
    res.push_back(path);
  } else {
    path.push_back(root->val);
    findPath(root->left, sum - root->val, path, res);
    findPath(root->right, sum - root->val, path, res);
  }
}

void Solution::findPathDFS(TreeNode* root, int sum, vector<vector<int>>& res) {
  stack<TreeNode*> trace;
  vector<int> path;
  int value = 0;
  TreeNode* last;
  while (root != NULL || !trace.empty()) {
    while (root != NULL) {
      trace.push(root);
      value += root->val;
      path.push_back(root->val);
      root = root->left;
    }
    root = trace.top();
    if (root->right != NULL && root->right != last) {
      root = root->right;
    } else {
      if (value == sum && root->left == NULL && root->right == NULL) {
        res.push_back(path);
      }

      last = trace.top();
      value -= last->val;
      trace.pop();
      path.pop_back();
      root = NULL;
    }
  }
}