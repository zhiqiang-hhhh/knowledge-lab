#include <iostream>
#include <memory>
#include <string>
#include <vector>

class heap {
 public:
  heap(size_t s);
  heap(std::initializer_list<int> il)
      : _spV(std::make_shared<std::vector<int>>(il)), heap_size(_spV->size()){ build_max_heap(_spV);};

  void sort();

  void print() {
    for (auto i : *_spV) std::cout << i << " ";
    std::cout << std::endl;
  }

 private:
  std::shared_ptr<std::vector<int>> _spV;
  size_t heap_size;
  void build_max_heap(std::shared_ptr<std::vector<int>>);
  void max_heapify(std::shared_ptr<std::vector<int>> A, size_t i);
#define parent(i) (i % 2) ? i >> 1 : (i >> 1) - 1;
#define left(i) (i << 1) + 1;
#define right(i) (i << 1) + 2;
};

void heap::sort(){
  size_t largest = heap_size;
  for(size_t i = largest - 1; i > 0; i--){
    int temp = _spV->front();
    _spV->front() = _spV->at(i);
    _spV->at(i) = temp;
    heap_size--;
    std::cout << heap_size << std::endl;
    max_heapify(_spV, 0);
  }
  heap_size = _spV->size();
}


// T(n) = O(n)
void heap::build_max_heap(std::shared_ptr<std::vector<int>> spV) {
  heap_size = spV->size();
  //
  size_t last_notLeaf = parent(heap_size);
  for (int i = last_notLeaf; i >= 0; i--) max_heapify(spV, i);
}

// T(n) = O(log n)
void heap::max_heapify(std::shared_ptr<std::vector<int>> spV, size_t i) {
  if (i >= heap_size) return;

  int rootval = spV->at(i);
  int li = left(i);
  int ri = right(i);
  size_t larger;
  if (li < heap_size && rootval < spV->at(li))
    larger = li;
  else
    larger = i;
  if (ri < heap_size && spV->at(larger) < spV->at(ri)) larger = ri;

  if (larger == i) return;
  int temp = spV->at(i);
  spV->at(i) = spV->at(larger);
  spV->at(larger) = temp;
  max_heapify(spV, larger);
}

int main() {
  heap h = {4, 5, 3, 2, 5, 6, 3, 7, 123, 43};
  h.print();

  h.sort();
  h.print();
}