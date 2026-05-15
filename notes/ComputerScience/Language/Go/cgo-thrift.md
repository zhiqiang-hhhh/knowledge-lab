# 利用 cgo 实现 NodeManager Client Go package 的可行性分析
[TOC]

cgo 为 go 语言提供了直接调用 c 语言库函数的能力。

其基本工作流程：
1. 在 Go 源码文件 main.go 中通过关键字 `import "C"` 告诉 Go toolchain 该代码引用了 C 函数实现；
2. main.go 通过 `C.fooFunc` 的方式声明 fooFunc 由 C 语言实现；
3. cgo 为 main.go 生成两份代码，一份 cgo_main.go，一份 cgo_main.c（示意名，实际不是）；
4. cgo_main.c 中包含所有通过 `C.xxx` 声明的函数，其定义需要 cgo 使用链接器查找，查找的目标 `.a` 文件需要在 main.go 中通过 `#cgo` 关键字指定
5. cgo_main.go 中包含对函数 `runtime.cgocall` 的调用，该函数是 Go 的系统库，包含对汇编代码的调用，作用是实现从 Go 到 C 函数的栈帧切换。

由于 cgo 只能提供调用 C 函数的能力，因此当 Go 需要调用 C++ 的实现时，我们需要提供 C 风格的头文件，然后在 .cpp 中实现类型转换。
所以从整体上来说，为了实现对 C++ library 的调用我们需要完成以下工作：

1. CWrapper.h：提供 fooFunc 的 C 语言声明；
2. CWrapper.cpp：fooFunc 的实现，接收 C 语言类型，并将其转为 C++ 类型（struct -> class)，并且调用 C++ 实现返回结果，可能还有 C++ 返回值类型的转换；
3. CgoWrapper.go：作用是为 main.go 提供 Go 函数调用，接受 Go 语言的类型，将其转换为 C 语言类型（Go struct -> C struct)，并且调用 C 实现返回结果，可能还有 C 返回值类型的转换；

NodeManager Client 中有 Thrift IDL 定义的类型，比如 DeployNode，如果要在 Golang 中使用该类型，最好的方法应当是由 thrift compiler 产生一份 gen-go 代码，提供该类型的 Go 实现，因此需要：

4. 修改编译工具链，由 thrift compiler 根据 .thrift 生成 gen-go

CWrapper.cpp 的后缀为 .cpp，g++ 编译该文件生成 .a 时会使用 C++ 规则对函数进行重命名，会导致 cgo 无法正确找到函数定义，需要使用 `extern "C"` 关键字包含 fooFunc 的实现，并且由于 CWrapper.h 会被 gcc/g++ 同时进行预处理，需要精细地通过编译器宏定义限制编译器行为。

5. 通过编译器宏定义限制编译行为

当涉及到对象状态改变时，需要通过在 Cpp <-> C <-> Go 之间传递指针，需要注意内存管理

6. 指针传递，内存管理

## cgo demo

用一个简单的 BookStore demo 来解释上述流程。我们有 BookStore.cpp/BookStore.h 的 Cpp Library 源码文件如下：
```c++
// BookStore.h
#include <string>
#include <vector>

struct Book
{
    std::string name;
    int64_t price;

    Book(char * name_, int64_t price_) : name(name_), price(price_){}
};

class BookStore
{
private:
    std::vector<Book> books;

public:
    BookStore() = default;
    BookStore(const std::vector<Book>& books_) : books(books_) {}

    bool hasBook(const Book& book);
    void addBook(const Book& book);
};

// BookStore.cpp
#include "Bookstore.h"

void BookStore::addBook(const Book &book_)
{
    books.push_back(book_);
}

bool BookStore::hasBook(const Book &book_)
{
    for (const auto& book : books)
    {
        if (book.name == book_.name)
            return true;
    }

    return false;
}
```
如果是 cpp 代码使用这个库，那么 main.cpp 如下：
```c++
#include "BookStore.h"

int main()
{
    BookStore bstore();

    Book book;
    book.name = std::string("Facebook");
    book.price = 100;

    bstore.addBook(book);
    if (bstore.hasBook(book))
    {
        std::cout << "Add book succeed\n";
    }
    else
        std::cout << "Add book failed\n";
    
}
```

现在我们想要利用 cgo 在 Golang 中使用这个 BookStore 库。

### BookStoreWrapper.cpp/h
BookStoreWrapper.h 对外提供 C 风格的接口，
```c
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>

struct Book;

void* initBookStore();
void* freeBookStore(void*);

bool hasBook(void* bookStore, struct Book* book);

void addBook(void* bookStore, struct Book* book);

struct Book* parse(char* name, int64_t);
```
* initBookStore/freeBookStore：前者 new 一个 BookStore 对象，并且将其指针作为 void * 返回给 Golong，后者用于释放 BookStore 资源；
* hasBook/addBook：C 风格的接口，要求 caller 传一个 initBookStore 创建的 void *，以及一个指向 Book 的指针；
* parse 函数用于使用 Golang 传递的参数构造一个 Book 对象。
```cpp
#include "Bookstore.h"
#include <string>

extern "C"
{

struct CBook {
    char* name;
    int64_t price;

    CBook(char* name_, int64_t price_) : name(name_), price(price_) {}
};

void* initBookStore()
{
    BookStore* res = new BookStore();
    return res;
}

void freeBookStore(void* bookStore)
{
    BookStore* ptr = static_cast<BookStore*>(bookStore);
    delete ptr;
    return;
}

bool hasBook(void* bookStore, CBook* cbook)
{
    BookStore* bstore = static_cast<BookStore*>(bookStore);

    Book book(cbook->name, cbook->price);
    return bstore->hasBook(book);
}

void addBook(void* bookStore, CBook* cbook)
{
    BookStore* bstore = static_cast<BookStore*>(bookStore);

    Book book(cbook->name, cbook->price);

    bstore->addBook(book);
}

CBook* parse(char* name_, int64_t price_) {
    return new CBook(name_, price_);
}

}
```
实现如上，注意必须使用 `extern "C"` 关键字修饰会被 cgo 链接的符号。

### BookStoreCgo.go
```golang
package cgo

/*
#cgo CFLAGS: -I/Users/hzq/go/src/cgo/pkg/C
#cgo LDFLAGS: -L/Users/hzq/go/src/cgo/pkg/C -lbookstore -lstdc++
#include "BookStoreWrapper.h"
*/
import "C"
import "unsafe"

type Book struct {
	Name  string
	Price int64
}

type BookStore struct {
	BookStoreCPtr unsafe.Pointer
}

// ParseBook Convert a Go struct Book to a C Book struct pointer
func ParseBook(book Book) *C.struct_CBook {
	cs := C.CString(book.Name)
	defer C.free(unsafe.Pointer(cs))
	var res = C.parse(cs, C.longlong(book.Price))
	return (*C.struct_CBook)(res)
}

func HasBook(bookStoreCPtr unsafe.Pointer, book Book) bool {
	cbook := ParseBook(book)
	return bool(C.hasBook(bookStoreCPtr, cbook))
}

func AddBook(bookStoreCPtr unsafe.Pointer, book Book) {
	cbook := ParseBook(book)
	C.addBook(bookStoreCPtr, cbook)
}

func InitBookStore() unsafe.Pointer {
	return C.initBookStore()
}
```
BookStoreCgo 为 main.go 提供 package。

* InitBookStore：Golang 中需要一个 BookStore 对象，该对象指向 C++ library 中的 BookStore 内存对象，通过保存 C.initBoookStore 返回的指针实现
* Book/BookStore Golang 中需要实现所有 C++ 库中相关的数据结构
* ParseBook：将一个 Golang 的 Book 类型转换为 BookStoreWrapper 中的 struct_CBook，实现时调用 BookStoreWrapper 中的 parse 函数
* HasBook/AddBook：Caller 调用，实现核心逻辑。

### main.go
```go
package main

import cgo "cgo/pkg"

func main() {
    bookStore := cgo.BookStore{}
    bookStore.BookStoreCPtr = cgo.InitBookStore()

    book := cgo.Book{
        Name:  "Book1",
        Price: 112,
    }

    cgo.AddBook(bookStore.BookStoreCPtr, book)

    if cgo.HasBook(bookStore.BookStoreCPtr, book) {
        println("Add succed")
    }

    cgo.FreeBookStore(bookStore)
    return
}
```
## Thrift 嵌套类型传递
从前面的 cgo demo 可以看到，比较麻烦的是 Go struct 到 C struct 以及 C++ Class 之间的转换，尤其是当涉及到 Thrfit 定义的复杂嵌套类型时，手写这些类型转换代码可能工作量巨大。利用 Thrift 的序列化协议可以解决 Thrift 类型的转换问题。

一个完整的利用 thrift 实现 Go 到 C++ 库的调用 demo 项目：https://github.com/roanhe-ts/cgo-rpc

Go thrift 把 Book 类型利用二进制协议写入到内存，然后将这段内存的地址与大小传给 Wrapper.cpp：
```go
func AddBook(bookStoreCPtr unsafe.Pointer, book thriftTypes.Book) {
	mem_buffer := thrift.NewTMemoryBufferLen(1024)
	protocol := thrift.NewTBinaryProtocolFactoryDefault().GetProtocol(mem_buffer)
	printAndPanicError(book.Write(defaultCtx, protocol))
	ptr := unsafe.Pointer(&mem_buffer.Bytes()[0])
	size := mem_buffer.Len()

	C.addBook(bookStoreCPtr, ptr, C.uint(size))
}
```
在 BookstoreWrapper.cpp 中，利用这段内存构造一个 Thrfit::TMemoryBuffer 对象，并且按照二进制协议把这个二进制对象反序列化成一个 Cpp 中的 Book
```c++
void addBook(void* bookStore, void* go_book, uint32_t size)
{
    uint8_t* binary_book = static_cast<uint8_t*>(go_book);
    std::shared_ptr<apache::thrift::transport::TMemoryBuffer> tmem_transport(
            new apache::thrift::transport::TMemoryBuffer(binary_book, size));
    std::shared_ptr<apache::thrift::protocol::TProtocol> tproto = create_deserialize_protocol(tmem_transport, false);
    CXX::Book cxxbook;
    try {
        cxxbook.read(tproto.get());
    } catch (std::exception& e) {
        std::cout << "Couldn't deserialize thrift msg: " << e.what() << std::endl;
        exit(-1);
    }
    
    BookStore* bstore = static_cast<BookStore*>(bookStore);
    bstore->addBook(cxxbook);

    std::cout << "Added book: ";
    cxxbook.printTo(std::cout);

    return;
}
```

## NodeManager cgo 

列出 NodeManager 中需要额外手写转换的类：
|类型|评估|
|--|--|
|NodeManagerClientConfig|里面有10多个成员变量，不过都是C++的基本类型或者std中的类型，需要手写 NodeManagerCiengConfig 的转换|
|MODEL::Endpoint|thrift类型，利用thrift完成转换|
|DeployStatus::type, ServiceStatus::type|枚举类型，需要手写转换|
|std::map<std::string, std::set\<std::string>>|std::map,std::set, 需要手写转换|
|std::map\<std::string, std::set\<int8_t\>>|手写转换|
|std::vector\<MODEL::Host\>|std::vector 需要手写转换|
|std::map<MODEL::ipv4_t, int32_t>|手写转换|
|std::vector\<std::string\>|手写转换|
|std::map\<MODEL::ModuleId::type, int32_t\>|手写转换|
|std::map\<MODEL::ModuleId::type, int8_t\>|手写转换|
|std::vector\<MODEL::DeployNode\>|定义 thrift 类型手写转换|

对于 map 与 vector，可以通过 thrift 的 map 与 list 完成类型转换，然后在 Wrapper.cpp 中用 thrift map/list 重新构造一个 std::map/std::vector

