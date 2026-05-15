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
  bool isValidBST(TreeNode* root) {
    resultType r = _isValidBST(root);
    return r.isBST;
  }

 private:
  struct resultType {
    bool isBST;
    TreeNode* minNode;
    TreeNode* maxNode;
    resultType(bool _t) : isBST(_t), minNode(NULL), maxNode(NULL) {}
  };

  resultType _isValidBST(TreeNode* root) {
    if (root == NULL) {
      return resultType(true);
    }

    resultType left = _isValidBST(root->left);
    resultType right = _isValidBST(root->right);

    if (!left.isBST || !right.isBST) {
      return resultType(false);
    }

    if (left.maxNode != NULL && left.maxNode->val >= root->val) {
      return resultType(false);
    }
    if (right.minNode != NULL && right.minNode->val <= root->val) {
      return resultType(false);
    }

    // is valid
    resultType r(true);
    r.minNode = left.minNode == NULL ? root : left.minNode;
    r.maxNode = right.maxNode == NULL ? root : right.maxNode;

    return r;
  }
};