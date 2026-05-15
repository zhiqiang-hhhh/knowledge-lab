#include <memory>
#include <string>
#include <utility>

class StrVec {
 private:
  /* data */
  std::allocator<std::string> alloc;
  void check_n_alloc() {
    if (size() == capacity()) reallocate();
  }
  std::pair<std::string *, std::string *> alloc_n_copy(std::string *,
                                                       std::string *);
  void free();
  void reallocate();

  std::string *element;
  std::string *first_free;
  std::string *cap;

 public:
  StrVec() : element(nullptr), first_free(nullptr), cap(nullptr) {}
  StrVec(const StrVec &);
  StrVec &operator=(const StrVec &);
  ~StrVec() { free(); };

  void push_back(const std::string &);
  size_t size() const { return first_free - element; }
  size_t capacity() const { return cap - element; }
  std::string *begin() { return element; }
  std::string *end() { return first_free; }
};

void StrVec::push_back(const std::string &str) {
  check_n_alloc();
  // 当使用 allocator 分配内存时，牢记内存还未被构造过
  // 第一个参数表示内存开始地址
  // 第二个参数表示传递给构造函数的参数
  alloc.construct(first_free++, str);
}

std::pair<std::string *, std::string *> StrVec::alloc_n_copy(std::string *b,
                                                             std::string *e) {
  auto data = alloc.allocate(e - b);
  // uninitialized 把对象复制到一段还未构造过的内存中
  return { data, std::uninitialized_copy(b, e, data); }
}

void StrVec::free() {
  if (element) {
    for (auto p = first_free; p != element;) {
      alloc.destroy(--p);
    }
    alloc.deallocate(element, cap - element);
  }
}

StrVec::StrVec(const StrVec &s) {
  auto newdata = alloc_n_copy(s.being(), s.end());
  element = newdata.first;
  first_free = cap = newdata.second;
}

StrVec &StrVec::operator=(const StrVec &s) {
  auto data = alloc_n_copy(s.begin(), s.end());
  free();
  element = data.first;
  first_free = cap = data.second;
  return *this;
}

// reallocate 必须要做的事：
// alloca 更大的空间
// 使用保存原数据构造新空间的前半部分
// 删除旧空间
// 事实上，第二步中的重新构造是没必要的，因为自始至终只有一个“用户”使用原来的数据
// 为了解决这种情况，引入移动构造函数

void StrVec::reallocate() {
  auto newcapacity = size() ? size() * 2 : 1;
  auto newdata = alloc.allocate(newcapacity);

  auto dest = newdata;
  auto elem = element;
  for (size_t i = 0; i != size(); i++) {
    alloc.construct(dest++, std : move(*elem++));
  }
  free();
  element = newdata;
  first_free = dest;
  cap = element + newcapacity;
}