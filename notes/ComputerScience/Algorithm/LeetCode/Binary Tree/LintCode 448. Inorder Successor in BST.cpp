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
  /*
   * @param root: The root of the BST.
   * @param p: You need find the successor node of p.
   * @return: Successor of p.
   */
  TreeNode* inorderSuccessor(TreeNode* root, TreeNode* p) {
    // write your code here
    if (root == nullptr || p == nullptr) return nullptr;

    if (p->right != nullptr) return TreeMinimum(p->right);

    stack<TreeNode*> track;
    track.push(nullptr);

    // 将 p 和 p 的所有祖先结点压栈
    TreeNode* tracer = root;
    while (tracer != p) {
      track.push(tracer);
      if (tracer->val < p->val)
        tracer = tracer->right;
      else
        tracer = tracer->left;
    }

    TreeNode* node = p;
    while (!track.empty()) {
      if (track.top() == nullptr || track.top()->left == node)
        return track.top();
      node = track.top();
      track.pop();
      if (node == track.top()->left) return track.top();
    }
  }

 private:
  TreeNode* TreeMinimum(TreeNode* root);
};

TreeNode* Solution::TreeMinimum(TreeNode* root) {
  while (root->left != nullptr) {
    root = root->left;
  }
  return root;
}