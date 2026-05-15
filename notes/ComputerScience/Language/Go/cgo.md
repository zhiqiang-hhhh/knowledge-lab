# 关于Go通过cgo调用C++代码的全面调查

* demo
* 性能测试
  * 测试用例
    * demo 
    * echo server (thrift/trpc)
    * Real working server
  * 性能差距分析
    * Go火焰图
    * 流程分析
    * 类型转换
* 可用性测试
  * 复杂数据类型
  * 内存垃圾回收
  * C语言固定栈帧 vs Go变长栈帧
  * Goroutine通过cgo调用阻塞系统调用
* 结论

## cgo 
```go
package rand

/*
#include <stdlib.h>
*/
import "C"

func Random() int {
    return int(C.random())
}

func Seed(i int) {
    C.srandom(C.uint(i))
}

```

"C"is a "pseudo-package", a special name interpreted by cgo as a reference to C’s name space.

C 标准库中的 random 函数返回一个 C 语言中的 long 类型，cgo 会将其表示为类型 C.long。该类型从当前 package 出去之前，需要被转为 Go 的数据类型。

```go
func Random() int {
    var r C.long = C.random()
    return int(r)
}
```

```go
package cgo

// #include <stdio.h>
// #include <stdlib.h>
import "C"
import "unsafe"

func Print(s string) {
	cs := C.CString(s)
	C.fputs(cs, (*C.FILE)(C.stdout))
	C.free(unsafe.Pointer(cs))
}
```
C 语言分配的堆内存空间 are not known to Go's memory manager.

https://golang.design/under-the-hood/zh-cn/part3tools/ch11compile/cgo/

https://chai2010.cn/advanced-go-programming-book/ch2-cgo/ch2-03-cgo-types.html

https://go.dev/blog/cgo

https://pkg.go.dev/cmd/cgo

https://cloud.tencent.com/developer/article/1650525

https://www.cockroachlabs.com/blog/the-cost-and-complexity-of-cgo/

https://dave.cheney.net/tag/cgo

https://github.com/changkun/cgo-benchmarks

https://juejin.cn/post/6974581261192921095