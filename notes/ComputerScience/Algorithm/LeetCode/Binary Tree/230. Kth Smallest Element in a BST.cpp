/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */
#include <stack>

class Solution {
 public:
  int kthSmallest(TreeNode* root, int _k) {
    k = _k;
    int res;
    inorder_Trav_K(root, res);
    return res;
  }

 private:
  priority_queue<int, vector<int>, less<int>> pq;
  int k;
  void inorder_Trav_K(TreeNode*, int& res);
};

void Solution::inorder_Trav_K(TreeNode* root, int& res) {
  if (root == nullptr) return;

  inorder_Trav_K(root->left, res);
  if (pq.size() < k) {
    pq.push(root->val);
    if (pq.size() < k) inorder_Trav_K(root->right, res);
  }
  res = pq.top();
  return;
}
