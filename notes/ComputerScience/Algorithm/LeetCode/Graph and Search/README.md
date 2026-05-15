## Copy Graph
源图是一个无向图，首先利用bfs获取所有节点，然后创建所有新节点，最后维护边。

遍历图时可能出现当前节点之前已经访问过的情况，所以需要一个 HashSet 保存所有之前访问过的节点。
```c++
/*
// Definition for a Node.
class Node {
public:
    int val;
    vector<Node*> neighbors;
    
    Node() {
        val = 0;
        neighbors = vector<Node*>();
    }
    
    Node(int _val) {
        val = _val;
        neighbors = vector<Node*>();
    }
    
    Node(int _val, vector<Node*> _neighbors) {
        val = _val;
        neighbors = _neighbors;
    }
};
*/

class Solution {
public:
    Node* cloneGraph(Node* node) {
        if(node == nullptr){
            return nullptr;
        }
        // 移动构造
        vector<Node*> nodes(std::move(bfsGetNodes(node)));
        
        // 旧node到新node的映射
        unordered_map<Node*, Node*> mapping;
        for(auto n : nodes){
            mapping[n] = new Node(n->val);
        }
        
        // 维护边的结构
        for(auto n : nodes){
            auto newnode = mapping[n];
            for(auto neighbor : n->neighbors){
                newnode->neighbors.push_back(mapping[neighbor]);
            }
        }
        return mapping[node];       
    }
private:
    vector<Node*> bfsGetNodes(Node* node){
        if(node == nullptr){
            return vector<Node*>();
        }
        queue<Node*> nodeQ;
        set<Node*> visited;
        vector<Node*> ret;
        
        nodeQ.push(node);
        visited.insert(node);
        
        while(!nodeQ.empty()){
            auto head = nodeQ.front();
            nodeQ.pop();
            ret.push_back(head);
            
            for(auto newnode : head->neighbors){
                if(visited.find(newnode) != visited.end()){
                    continue;
                }
                visited.insert(newnode);
                nodeQ.push(newnode);                
            }
        }
        return ret;
    }
};
```