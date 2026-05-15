/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode(int x) : val(x), next(NULL) {}
 * };
 */

#include <iostream>
struct ListNode {
  int val;
  ListNode* next;
  ListNode(int x) : val(x), next(nullptr){};
};

/*merge sort*/
class Solution {
 public:
  ListNode* sortList(ListNode* head) {}

 private:
  // 730ms, 30.2MB
  struct ListNode* quickSortC(struct ListNode*);
  struct ListNode* partitionC(struct ListNode*);
  // 770ms, 32MB
  ListNode* quickSort(ListNode*);
  ListNode* partition(ListNode*);

  // 
  ListNode* mergeSort(ListNode*);
  ListNode* findMid(ListNode*);
  ListNode* merge(ListNode*, ListNode*);
};

struct ListNode* Solution::quickSortC(struct ListNode* head) {
  if (head == NULL || head->next == NULL) return head;

  struct ListNode* new_head = partitionC(head);

  struct ListNode* ghead = quickSortC(head->next);
  head->next = NULL;
  struct ListNode* lhead = quickSortC(new_head);
  head->next = ghead;

  return lhead;

}

struct ListNode* Solution::partitionC(struct ListNode* head){
    if(head == NULL || head->next == NULL) return head;
    int key = head->val;

    struct ListNode* dummyL = (struct ListNode*)malloc(sizeof(struct ListNode));
    struct ListNode* dummyG = (struct ListNode*)malloc(sizeof(struct ListNode));
    struct ListNode* tailL = dummyL;
    struct ListNode* tailG = dummyG;

    while(head != NULL){
        if(head->val < key){
            tailL->next = head;
            tailL = tailL->next;
        }
        else{
            tailG->next = head;
            tailG = tailG->next;
        }
        head = head->next;
    }

    tailG->next = NULL;
    tailL->next = dummyG->next;

    struct ListNode* r = dummyL->next;
    free(dummyL);
    free(dummyG);

    return r;
}



ListNode* Solution::quickSort(ListNode* head) {
  if (head == NULL || head->next == NULL) return head;

  ListNode* p = partition(head);  // use head->val as key value

  ListNode* dummyG = new ListNode(0);
  ListNode* dummyL = new ListNode(0);

  dummyG->next = quickSort(head->next);
  head->next = NULL;
  dummyL->next = quickSort(p);

  head->next = dummyG->next;
  ListNode* r = dummyL->next;

  delete (dummyL);
  delete (dummyG);

  return r;
}

ListNode* Solution::partition(ListNode* head) {
  if (head == NULL || head->next == NULL) return head;

  int key = head->val;  // use head->val as key value

  ListNode* dummyL = new ListNode(0);  // less val nodes list
  ListNode* tailL = dummyL;

  ListNode* dummyG = new ListNode(0);  // greater val nodes list
  ListNode* tailG = dummyG;

  while (head != NULL) {
    if (head->val < key) {
      tailL->next = head;
      tailL = tailL->next;
    } else {
      tailG->next = head;
      tailG = tailG->next;
    }
    head = head->next;
  }

  /*insert previous head node to the end of less val list*/
  tailG->next = NULL;
  tailL->next = dummyG->next;

  delete (dummyG);
  ListNode* r = dummyL->next;
  delete (dummyL);
  return r;
}

ListNode* Solution::mergeSort(ListNode* head) {
  if (head == NULL || head->next == NULL) return head;

  ListNode* midPos = findMid(head);
  ListNode* ghead = midPos->next;
  midPos->next = NULL;

  ListNode* lhead = mergeSort(head);
  ghead = mergeSort(ghead);

  return merge(lhead, ghead);
}

ListNode* Solution::findMid(ListNode* head) {
  // 这里 fast 指针必须初始化为 head->next
  // 如果 fast = head，则当 List 包含两个元素时，返回值将是指向第二个元素的指针
  // 结合 mergeSort 的逻辑，将会产生无限循环
  ListNode *slow = head, *fast = head->next;
  while (fast != NULL && fast->next != NULL) {
    fast = fast->next->next;
    slow = slow->next;
  }
  return slow;
}

ListNode* Solution::merge(ListNode* l1, ListNode* l2) {
  ListNode* dummy = new ListNode(0);
  ListNode* tail = dummy;
  while (l1 != NULL && l2 != NULL) {
    if (l1->val < l2->val) {
      tail->next = l1;
      l1 = l1->next;
    } else {
      tail->next = l2;
      l2 = l2->next;
    }
    tail = tail->next;
  }
  if (l1 != NULL)
    tail->next = l1;
  else
    tail->next = l2;

  ListNode* r = dummy->next;
  delete (dummy);

  return r;
}
