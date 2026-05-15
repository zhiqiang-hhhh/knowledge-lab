<!-- TOC -->

- [Binary Tree 与分治法](#binary-tree-%e4%b8%8e%e5%88%86%e6%b2%bb%e6%b3%95)
  - [94. Binary Tree Inorder Traversal](#94-binary-tree-inorder-traversal)
    - [173. Binary Search Tree Iterator](#173-binary-search-tree-iterator)
  - [145. Binary Tree Postorder Traversal](#145-binary-tree-postorder-traversal)
    - [112. Path Sum](#112-path-sum)
    - [113. Path Sum II](#113-path-sum-ii)
- [Binary Search Tree](#binary-search-tree)
  - [98. Validate Binary Search Tree](#98-validate-binary-search-tree)
  - [LintCode 448. Inorder Successor in BST](#lintcode-448-inorder-successor-in-bst)
  - [102. Binary Tree Level Order Traversal](#102-binary-tree-level-order-traversal)
    - [103. Binary Tree Zigzag Level Order Traversal](#103-binary-tree-zigzag-level-order-traversal)

<!-- /TOC -->
## Binary Tree 与分治法

二叉树最基本最关键的永远是前中后序遍历的非递归写法。
### 94. Binary Tree Inorder Traversal
```c++
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
        
        while(root != nullptr || !track.empty()){
            while(root != nullptr){
                trace.push(root);
                root = root->left;
            }

            // trace 中的节点是从根到叶子左子树顺序压入
            // 当某个结点位于 trace.top()，即表示该节点的所有左子树已经遍历完毕
            // 所以返回值就是当前 trace.top 的 value
            // 下一步该查找的则是当前结点的右子树根结点
            auto temp = trace.top();
            trace.pop();
            res.push_back(temp->val);
            root = temp->right;        
        }
        return res;
    }
};
```

#### 173. Binary Search Tree Iterator
```c++
/**
 * Definition for a binary tree node.
 * struct TreeNode {
 *     int val;
 *     TreeNode *left;
 *     TreeNode *right;
 *     TreeNode(int x) : val(x), left(NULL), right(NULL) {}
 * };
 */
class BSTIterator {
private:
    TreeNode* cure;
    stack<TreeNode*> trace;
public:
    BSTIterator(TreeNode* root) : cure(root), trace() {
    }
    
    /** @return the next smallest number */
    int next() {
        while(cure != NULL){
            trace.push(cure);
            cure = cure->left;    
        }
            
        // trace 中的节点是从根到叶子左子树顺序压入
        // 当某个结点位于 trace.top()，即表示该节点的所有左子树已经遍历完毕
        // 所以返回值就是当前 trace.top 的 value
        // 下一步该查找的则是当前结点的右子树根结点
        TreeNode* temp = trace.top();
        trace.pop();
        int v = temp->val;
        cure = temp->right;
        return v;
    }
    
    /** @return whether we have a next smallest number */
    bool hasNext() {
        if(cure != NULL || !trace.empty())
            return true;
        
        return false;
    }
};

/**
 * Your BSTIterator object will be instantiated and called as such:
 * BSTIterator* obj = new BSTIterator(root);
 * int param_1 = obj->next();
 * bool param_2 = obj->hasNext();
 */
```


### 145. Binary Tree Postorder Traversal
```c++
void Solution::postorderTraversal_Iteration(TreeNode* root, vector<int>& res) {
  stack<TreeNode*> track;
  TreeNode* last = nullptr;  // 记录上次被读值的节点

  // root 不为空或者 trece 不为空都表示还没有遍历完所有结点
  // 
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
```
#### 112. Path Sum
本题和 113 做法一致，区别在于本题不需要找到具体路径，只需要返回有没有。
```c++
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
```
#### 113. Path Sum II
给定一个二叉树，以及一个 targetSum，寻找是否有**从根到叶子的**路径，路径元素和等于 targetSum，如果有，**找出所有路径**。
本题有两种做法：
1. 分治法
    在左子树和右子树中分别寻找子路径，子路径元素和应该等于 targeSum - root.val
    当叶子节点 leaf.val == targetSum 时，说明找到一条路径
2. 后序遍历
    采用后序遍历的迭代做法，用一个变量 value 记录从根结点到当前节点路径元素和，如果 value == targetSum，且当前结点为叶节点，那么就找到了一条路径

```c++
class Solution {
 public:
  vector<vector<int>> pathSum(TreeNode* root, int sum) {
    vector<vector<int>> res;
    // findPathRecursion(root, sum , res);
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
```


## Binary Search Tree
二叉搜索树的定义

二叉查找树或者是一棵空树，或者是这样一棵树：若它的左子树不空，则左子树上所有结点的值均小于它的根结点的值； 若它的右子树不空，则右子树上所有结点的值均大于它的根结点的值； 它的左、右子树也分别为二叉排序树。

可以看出二叉查找树本身就是递归定义的。

### 98. Validate Binary Search Tree
二叉查找树本身是递归定义的，因此按照递归来验证某棵树是否为合法二叉查找树。
```c++
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
    
private:
    struct resultType{
        bool isBST;
        TreeNode* minNode;
        TreeNode* maxNode;
        resultType(bool _t) : isBST(_t), minNode(NULL), maxNode(NULL){}
    };
public:
    bool isValidBST(TreeNode* root){
        resultType r = _isValidBST(root);
        return r.isBST;
    }
    resultType _isValidBST(TreeNode* root) {
        if(root == NULL){
            return resultType(true);
        }
        
        resultType left = _isValidBST(root->left);
        resultType right = _isValidBST(root->right);
        
        if(!left.isBST || !right.isBST){
            return resultType(false);
        }
        
        if(left.maxNode != NULL && left.maxNode->val >= root->val){
            return resultType(false);
        }
        if(right.minNode != NULL && right.minNode->val <= root->val){
            return resultType(false);
        }
        
        // is valid
        resultType r(true);
        r.minNode = left.minNode == NULL ? root : left.minNode;
        r.maxNode = right.maxNode == NULL ? root : right.maxNode;
        
        return r;
    }
};
```
### LintCode 448. Inorder Successor in BST
本题是给出 BST 中一个随机结点 p，求 p 的中序后继。
第一步肯定是在 BST 中找到 p，并且将来时的路径压栈。
但是这样的到的栈与正常 inorder 访问到 p 时得到的栈不同。

主要不同点在于：后者得到的栈中的所有结点一定都是按照中序遍历还未访问过的，且一定都是 p 之后的结点；而前者得到的栈中的结点会包含 p 之前的结点，即按照中序遍历顺序是，应该在 p 之前被访问。

如果 trace.top1 是 trace.top2 的右孩子，那么说明 trace.top2 应该在 trace.top1 之前被访问，所以这两个结点都不应该在 trace 中。当 trace.top1 是 trace.top2 的左孩子时，则说明 trace.top2 一定是 trace.top1 的中序后继。

```c++
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
    TreeNode * inorderSuccessor(TreeNode * root, TreeNode * p) {
        // write your code here
        if(root == nullptr || p == nullptr)
            return nullptr;
            
        if(p->right != nullptr){
            p = p->right;
            while(p->left != nullptr){
                p = p->left;
            }
            return p;
        }
            
        stack<TreeNode*> trace;
        while(root != nullptr){
            if(root->val < p->val){
                trace.push(root);
                root = root->right;
            }else if(root->val > p->val){
                trace.push(root);
                root = root->left;
            }else{
                root = nullptr;
            }
        }
        
        TreeNode* ot = p;
        while(!trace.empty()){
            TreeNode* nt = trace.top();
            if(ot == nt->right){
                ot = nt;
                trace.pop();
            }else{
               return nt; 
            }       
        }
        return nullptr;
    }
};
```

### 102. Binary Tree Level Order Traversal
二叉树的宽度优先搜索。借助队列完成。
```c++
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
    vector<vector<int>> levelOrder(TreeNode* root) {
        vector<vector<int>> res;
        if(root == NULL)
            return res;
        
        queue<TreeNode*> q;
        q.push(root);
        
        while(!q.empty()){
            int size = (int)q.size();
            vector<int> cureLevel;
            for(int i = 1; i <= size; i++){
                TreeNode* n = q.front();
                cureLevel.push_back(n->val);
                q.pop();
                if(n->left != NULL)
                    q.push(n->left);
                if(n->right != NULL)
                    q.push(n->right);
            }
            res.push_back(cureLevel);
        }
        return res;
    }
};
```
有时会考察使用深度优先搜索来完成宽度优先搜索
```c++
// DFS
class Solution {
public:
    vector<vector<int>> levelOrder(TreeNode* root) {
        vector<vector<int>> res;
        if(root == NULL)
            return res;
        
        for(int i = 0;;i++){
            vector<int> level;
            dfs(root, level, 0, i);
            if(level.size() == 0)
                break;
            res.push_back(level);
        }
        return res;        
    }
    void dfs(TreeNode* root, vector<int>& level, int cure, int max){
        if(root == NULL)
            return;
        if(cure == max){
            level.push_back(root->val);
        }
        
        dfs(root->left, level, cure + 1, max);
        dfs(root->right, level, cure + 1, max);
    }
};
```
#### 103. Binary Tree Zigzag Level Order Traversal
本题要求换方向的层次遍历

    For example:
    
    Given binary tree [3,9,20,null,null,15,7],
            3
           / \
          9  20
            /  \
           15   7
    return its zigzag level order traversal as:
    [
        [3],
        [20,9],
        [15,7]
    ]
借助 deque
```c++
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
    vector<vector<int>> zigzagLevelOrder(TreeNode* root) {
        vector<vector<int>> res;
        if(root == NULL)
            return res;
        
        deque<TreeNode*> dq;
        dq.push_back(root);
        bool forward = true;
        while(!dq.empty()){
            size_t size = dq.size();
            vector<int> level;
            if(forward){
                for(int i = 1; i <= size; i++){
                    TreeNode* temp = dq.front();
                    dq.pop_front();
                    level.push_back(temp->val);
                    if(temp->left != NULL)
                        dq.push_back(temp->left);
                    if(temp->right != NULL)
                        dq.push_back(temp->right);
                }
            }else{
               for(int i = 1; i <= size; i++){
                    TreeNode* temp = dq.back();
                    dq.pop_back();
                    level.push_back(temp->val);
                   if(temp->right != NULL)
                        dq.push_front(temp->right);
                    if(temp->left != NULL)
                        dq.push_front(temp->left);        
               }
            }

            forward = !forward;
            res.push_back(level);            
        }
        return res;
    }
};
```