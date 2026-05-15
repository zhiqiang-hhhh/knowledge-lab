GNU 多精度库 gmp 的整型类型 mpz_t 的 cgo 封装。使其看起来像 Go package 的

```go
// #include <gmp.h>
import "C"
```
是对 cgo 的型号。

Cgo recognizes any use of a qualified identifier C.xxx and use gcc to find the definition of xxx.
If xxx is a type, cgo replaces C.xxx with a Go translation.

C arithmetic types -> Precisely-sized Go arithmetic types.
C struct -> Go struct, field by field, nrepresentable fields are replaced with opaque byte arrays.
C union -> Go struct containing the first union member and perhaps additional padding
C arrays -> Go arrays.
C pointers -> Go pointers.
C function pointers -> Go unitptr
C void pointer -> Go unsafe.Pointer

```c
typedef unsigned long int mp_limb_t;

typedef struct
{
    int _mp_alloc;
    int _mp_size;
    mp_limb_t *_mp_d;
} __mpz_struct;

typedef __mpz_struct mpz_t[1];
```
Cgo 会产生一个新的 C struct如下：
```c
type _C_int int32
type _C_mp_limb_t uint64
type _C___mpz_struct struct {
    _mp_alloc _C_int;
    _mp_size _C_int;
    _mp_d *_C_mp_limb_t;
}
type _C_mpz_t [1]_C___mpz_struct
```
然后把所有的 C.__mpz_struct 替换为 _C__mpz_struct

如果 xxx 是一个变量而不是一个类型，那么 cgo 会安排 C.xxx 指向对应的 C 变量。
比如，假如 gmp library 提供了
```c
mpz_t zero;
```
那么cgo会为go中的 C.zero 如下代码
```go
var _C_zero *C.mpz_t
```
然后把所有的 C.zero 替换为 (*_C_zero)

It is fine for the Go world to have pointers into the C world and to free those pointers when they are no longer needed.  To help, the Go code can define Go objects holding the C pointers and use runtime.SetFinalizer on those Go objects.

It is much more difficult for the C world to have pointers into the Go
world, because the Go garbage collector is unaware of the memory
allocated by C.  The most important consideration is not to
constrain future implementations, so the rule is that Go code can
hand a Go pointer to C code but must separately arrange for
Go to hang on to a reference to the pointer until C is done with it.


-------

```go
type Int struct {
    i       C.mpz_t
    init    bool
}
```
对应的 C定义：
```c
typedef struct
{
  int _mp_alloc;	
  int _mp_size;
  mp_limb_t *_mp_d;
} __mpz_struct;

typedef __mpz_struct mpz_t[1];
```
mpz_t 是 C 的数组类型，mpz_t 数组大小为 1 ，元素类型为 __mpz_struct

```golang
func (z *Int) doinit() {
	if z.init {
		return
	}
	z.init = true
	C.mpz_init(&z.i[0])
}
```
`C.mpz_init(&z.i[0])`这里说明在Golang里是认识C中声明的数组类型的，
```c
typedef __mpz_struct *mpz_ptr;

__GMP_DECLSPEC void mpz_init (mpz_ptr) __GMP_NOTHROW;
```
`mpz_init`在C中形参为指向 C 中 __mpz_struct 的指针。这说明在Golang中对某个C类型的变量直接取地址，得到的指针是一个C指针。