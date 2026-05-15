Go 向 C 代码传递指针的原则：
* The Go garbage collector must be aware of the location of all Go pointers, except for a known set of pointers that are temporarily visible to C code. The pointers visible to C code exist in an area that the garbage collector can not see, and the garbage collector may not modify or release them.

如果Golang代码不引入 unsafe package或者不使用C时，上述原则很难被打破。

1. Go code 可以向 C 提供指针，但是，这个指针指向的Go mamory中不能包涵任何的Go pointers
   * The C code must not store any Go pointers in Go memory, even temporarily.
   * When passing a pointer to a field in a struct, the Go memory in question is the memory occupied by the field, not the entire struct.
   * When passing a pointer to an element in an array or slice, the Go memory in question is the entire array or the entire backing array of the slice.
   * Passing a Go pointer to C code means that that Go pointer is visible to C code; passing one Go pointer does not cause any other Go pointers to become visible.
   * The maximum number of Go pointers that can become visible to C code in a single function call is the number of arguments to the function.

2. C code may not keep a copy of a Go pointer after the call returns
   * A Go pointer passed as an argument to C code is only visible to C code for the duration of the function call.
  
3. A Go function called by C code may not return a Go pointer.
    * A Go function called by C code may take C pointers as arguments, and it may store non-pointer or C pointer data through those pointers, but it may not store a Go pointer in memory pointed to by a C pointer.