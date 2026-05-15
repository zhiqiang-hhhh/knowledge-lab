#include <iostream>

class treeNode{
 public:
    treeNode *p, *l, *r;
    int val;
};

void inorder_Tree_Walk(treeNode *n){
    if(n == nullptr) return;
    inorder_Tree_Walk(n->l);
    std::cout << n->val;
    inorder_Tree_Walk(n->r);
}

treeNode* tree_Search(treeNode* x, const int k){
    if(x==nullptr || x->val == k) return x;
    if(k < x->val) return tree_Search(x->l, k);
    return tree_Search(x->r, k);
}

treeNode* iterative_Tree_Search(treeNode* x, const int k){
    while(x != nullptr && k != x->val){
        if(k < x->val) x = x->l;
        else x = x->r;
    }
    return x;
}