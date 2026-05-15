#include <memory>
#include <vector>

template <typename T>
class Blob {
 public:
  typedef T value_type;
  typedef std::vector<T>::size_type size_type;
  Blob();
  Blob(std::initializer_list<T> i1);
  size_type size() const { return data->size; }

  bool empty() const { return data->empty(); }
  void push_back(const T& t){ data->push_back(t);}
 private:
  std::shared_ptr<std::vector<T>> data;
};