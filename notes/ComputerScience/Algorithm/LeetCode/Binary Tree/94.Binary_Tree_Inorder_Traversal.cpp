#include<vector>
#include<iostream>
#include<string>
using namespace std;
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
    stack<TreeNode*> track;

    while (root != nullptr || !track.empty()) {
      while (root != nullptr) {
        track.push(root);
        root = root->left;
      }

      TreeNode* temp = track.top();
      track.pop();
      res.push_back(track->val);
      root = temp->right;
    }

    return res;
  }

 private:
  void inorderTraversal_Recur(TreeNode* root, vector<int>& res);
};

void Solution::inorderTraversal_Recur(TreeNode* root, vector<int>& res) {
  if (root == nullptr) return;

  inorderTraversal_Recur(root->left, res);
  res.push_back(root->val);
  inorderTraversal_Recur(root->right, res);
}
