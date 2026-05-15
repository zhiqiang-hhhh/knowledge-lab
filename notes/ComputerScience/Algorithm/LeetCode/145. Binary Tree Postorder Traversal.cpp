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
  vector<int> postorderTraversal(TreeNode* root) {
    vector<int> res;
    postorderTraversal_Iteration(root, res);
    return res;
  }

 private:
  void postorderTraversal_Recursion(TreeNode* root, vector<int>& res);
  void postorderTraversal_Iteration(TreeNode* root, vector<int>& res);
};

void Solution::postorderTraversal_Recursion(TreeNode* root, vector<int>& res) {
  if (root == nullptr) return;
  postorderTraversal_Recursion(root->left, res);
  postorderTraversal_Recursion(root->right, res);
  res.push_back(root->val);
}

void Solution::postorderTraversal_Iteration(TreeNode* root, vector<int>& res) {
  stack<TreeNode*> track;
  TreeNode* last = nullptr;  // 记录上次被读值的节点

  // root 不为空表示当前是第一次访问 Tree
  // trace 不为空表示还没有遍历完所有结点
  while (root != nullptr || !track.empty()) {
    while (root != nullptr) {
      track.push(root);
      root = root->left;
    }

    // track.top 结点的左子树永远是被访问过的
    // 如果这里复用 root，那么需要在循环最后执行 root = NULL
    TreeNode* node = track.top();

    // root->right 存在，且 root 的右子树没有被遍历过
    // 则遍历 root 右子树先
    if (node->right != nullptr && last != node->right) {
      root = node->right;
    }
    // 否则说明 node 的左右子树都已经被遍历
    // res.push_back 记录 node->val
    else {
      res.push_back(node->val);
      last = node;
      track.pop();
      // root = NULL
    }
  }
}