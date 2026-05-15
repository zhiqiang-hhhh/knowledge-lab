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
  bool findTarget(TreeNode* root, int k) {
    if (root == NULL) return false;
    bstIterator left(root, true);
    bstIterator right(root, false);

    int a = left.next();
    int b = right.next();
    while (a < b) {
      if (a + b == k) {
        return true;
      } else if (a + b < k) {
        a = left.next();
      } else {
        b = right.next();
      }
    }
    return false;
  }

 private:
  class bstIterator {
   private:
    TreeNode* cure;
    stack<TreeNode*> trace;
    bool forward;

   public:
    bstIterator(TreeNode* root, bool _d) : cure(root), trace(), forward(_d) {}
    int next() {
      while (cure != NULL) {
        trace.push(cure);
        cure = forward ? cure->left : cure->right;
      }
      if (trace.empty()) return INT_MIN;
      TreeNode* temp = trace.top();
      int v = temp->val;
      trace.pop();
      cure = forward ? temp->right : temp->left;
      return v;
    }

    bool hasNext() {
      if (cure != NULL || !trace.empty()) return true;
      return false;
    }
  };
};