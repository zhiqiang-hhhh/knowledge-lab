#include <string>
#include <memory>

class StrVec{
public:
    StrVec():
        elements(nullptr), first_free(nullptr), cap(nullptr) {}
    StrVec(const StrVec &);             //拷贝构造函数
    StrVec &operator=(const StrVec &);  //拷贝赋值运算符
    ~StrVec();                          //析构函数

    void push_back(const std::string &);                    //拷贝元素
    size_t size() const { return first_free - elements; }
    size_t capacity() const { return cap - elements; }
    std::string *begin() const { return elements; }
    std::string *end() const { return first_free; }

private:
    static std::allocator<std::string> alloc;
    void chk_n_alloc()
    {   
        if(size() == capacity())
            reallocate();
    };
    std::pair<std::string *, std::string *> alloc_n_copy (const std::string *, const std::string *);
    void free();       //销毁元素并释放内存
    void reallocate(); //获取更多内存并拷贝已有内存

    std::string *elements;
    std::string *first_free;
    std::string *cap;
};

void StrVec::push_back(const std::string &s)
{
    chk_n_alloc();
    alloc.construct(first_free++, s);
}
std::pair<std::string *, std::string *>
StrVec::alloc_n_copy(const std::string *b, const std::string *e)
{
    auto data = alloc.allocate(e - b);
    return {data, std::uninitialized_copy(b, e, data)};
}

void StrVec::free()
{
    if(elements){
        for (auto p = first_free; p != elements; )
            alloc.destroy(--p);
        alloc.deallocate(elements, cap - elements);
    }
}