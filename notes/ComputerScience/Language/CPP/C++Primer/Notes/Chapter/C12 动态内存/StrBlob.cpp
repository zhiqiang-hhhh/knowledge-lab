#include <fstream>
#include <initializer_list>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
class StrBlobPtr;

class StrBlob {
  friend class StrBlobPtr;

 public:
  typedef std::vector<std::string>::size_type size_type;
  StrBlob() : data(std::make_shared<std::vector<std::string>>()){};
  StrBlob(std::initializer_list<std::string> il)
      : data(std::make_shared<std::vector<std::string>>(il)){};
  size_type size() const { return data->size(); }
  bool empty() const { return data->empty(); }

  void push_back(const std::string &t) { data->push_back(t); }
  void pop_back();

  std::string &front() const;
  std::string &back() const;

  StrBlobPtr begin();
  StrBlobPtr end();

 private:
  std::shared_ptr<std::vector<std::string>> data;
  void check(size_type i, const std::string &msg) const;
};

class StrBlobPtr {
 public:
  StrBlobPtr() : curr(0) {}
  StrBlobPtr(StrBlob &stb, size_t i = 0) : wptr(stb.data), curr(i) {}
  std::string &deref() const;
  StrBlobPtr &incr();
  bool operator==(StrBlobPtr &);

 private:
  std::shared_ptr<std::vector<std::string>> check(std::size_t,
                                                  const std::string &) const;
  std::weak_ptr<std::vector<std::string>> wptr;
  std::size_t curr;
};

// check 检查索引 i 是否超出对象索引的最大范围
std::shared_ptr<std::vector<std::string>> StrBlobPtr::check(
    std::size_t i, const std::string &msg) const {
  auto ret = wptr.lock();
  if (!ret) throw std::runtime_error("unbound StrBlobPtr");
  if (i >= ret->size()) throw std::out_of_range(msg);
  return ret;
}

std::string &StrBlobPtr::deref() const {
  auto t = check(curr, "dereference past end");
  return (*t)[curr];
}

StrBlobPtr &StrBlobPtr::incr() {
  check(curr, "increment past end of StrBlobPtr");
  ++curr;
  return *this;
}

bool StrBlobPtr::operator==(StrBlobPtr &stp) {
  if (stp.wptr.lock() == wptr.lock() && stp.curr == curr) return true;
  return false;
}

StrBlobPtr StrBlob::begin() { return StrBlobPtr(*this); }
StrBlobPtr StrBlob::end() { return StrBlobPtr(*this, data->size()); }

int main(int argc, char *argv[]) {
  if (argc != 2) {
    std::cout << "Wrong Format\n";
    return 1;
  }

  std::ifstream infile(argv[1]);
  if (!infile) {
    std::cout << "Open File Error\n";
    return 1;
  }

  std::string inbuffer;

  StrBlob blob;
  StrBlobPtr blobptr = blob.begin();

  while (getline(infile, inbuffer)) {
    inbuffer.push_back('\n');
    blob.push_back(inbuffer);
  }

  StrBlobPtr blobend = blob.end();
  // std::cout << blobend.deref();

  try {
    while (!(blobptr == blobend)) {
      std::cout << blobptr.deref();
      blobptr.incr();
    }
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
  }
}