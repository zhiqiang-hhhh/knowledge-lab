#include <initializer_list>
#include <memory>
#include <stdexcept>
#include <vector>

class StrBlob {
 public:
  typedef std::vector<std::string>::size_type size_type;
  StrBlob() : data(std::make_shared<std::vector<std::string>>()) {}
  StrBlob(std::initializer_list<std::string> i1)
      : data(std::make_shared<std::vector<std::string>>(i1)) {}
  size_type size() const { return data->size(); }
  bool empty() const { return data->empty(); }

  void push_back(const std::string &t) { data->push_back(t); }
  void pop_back();

  std::string front();
  std::string back();

 private:
  std::shared_ptr<std::vector<std::string>> data;
  void check(size_type i, const std::string &msg) const;
};

void StrBlob::pop_back() {
  check(0, "Pop back on empty StrBlob\n");
  data->pop_back();
}

std::string StrBlob::front() {
  check(0, "StrBlob is empty\n");
  return data->front();
}

std::string StrBlob::back() {
  check(0, "StrBlob is empty\n");
  return data->back();
}

void StrBlob::check(StrBlob::size_type i, const std::string &msg) const {
  if (i >= data->size()) throw std::out_of_range(msg);
}