[TOC]

链接时常见的一类问题是符号的重复定义。如果该符号的定义确实在各个目标文件中一样，那么只需要在源码中将重复的定义删除就行了。但是如果由于各种原因，我们需要保留该符号的不同定义，同时还要要求链接器能够正确链接对应的不同版本，那问题就不好解决了。

首先必须了解，如果传递给链接器的重定位目标文件中有重复定义的强类型符号，那么链接器会报错；如果是多个静态链接库（.a）中有重复定义的强类型符号，那么链接不会报错，而是选择找到的第一个定义。这里的强类型是在链接器的语境下的符号类型，在本文中可以简单理解为是不被 static 修饰的 .cpp 文件中的函数名以及全局的有显示初始化的变量。

### 情景一 重命名符号表
bitshuffle 这个库在具有 avx2 指令支持的硬件上具有很好的性能提升，为了使用这些指令需要在编译 bitshuffle 的时候添加 `-mavx2` 参数。 Doris 引用到了这个库，从 Doris 的角度出发，为了让自己分发出去的二进制能够兼容两类硬件，需要在最后的可执行文件里同时保留两份 bitshuffle 的代码，在可执行文件加载时根据硬件类型决定调用哪份代码。但是由于两份定义同时存在，这给链接造成了困难。

Doris 的思路是在添加一层 [bitshuffle warpper](https://github.com/doris-vectorized/doris-vectorized/blob/2ce8e2524e9711567153ba84de77880978f72a55/be/src/olap/rowset/segment_v2/bitshuffle_wrapper.cpp)，代码详细如下：
```c++
// Licensed to the Apache Software Foundation (ASF) under one
// or more contributor license agreements.  See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership.  The ASF licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License.  You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied.  See the License for the
// specific language governing permissions and limitations
// under the License.

#include "olap/rowset/segment_v2/bitshuffle_wrapper.h"

// Include the bitshuffle header once to get the default (non-AVX2)
// symbols.
#include <bitshuffle/bitshuffle.h>

#include "gutil/cpu.h"

// Include the bitshuffle header again, but this time importing the
// AVX2-compiled symbols by defining some macros.
#undef BITSHUFFLE_H
#define bshuf_compress_lz4_bound bshuf_compress_lz4_bound_avx2
#define bshuf_compress_lz4 bshuf_compress_lz4_avx2
#define bshuf_decompress_lz4 bshuf_decompress_lz4_avx2
#include <bitshuffle/bitshuffle.h> // NOLINT(*)
#undef bshuf_compress_lz4_bound
#undef bshuf_compress_lz4
#undef bshuf_decompress_lz4

using base::CPU;

namespace doris {
namespace bitshuffle {

// Function pointers which will be assigned the correct implementation
// for the runtime architecture.
namespace {
    decltype(&bshuf_compress_lz4_bound) g_bshuf_compress_lz4_bound;
    decltype(&bshuf_compress_lz4) g_bshuf_compress_lz4;
    decltype(&bshuf_decompress_lz4) g_bshuf_decompress_lz4;
} // anonymous namespace

// When this translation unit is initialized, figure out the current CPU and
// assign the correct function for this architecture.
//
// This avoids an expensive 'cpuid' call in the hot path, and also avoids
// the cost of a 'std::once' call.
__attribute__((constructor)) void SelectBitshuffleFunctions() {
#if (defined(__i386) || defined(__x86_64__))
    if (CPU().has_avx2()) {
        g_bshuf_compress_lz4_bound = bshuf_compress_lz4_bound_avx2;
        g_bshuf_compress_lz4 = bshuf_compress_lz4_avx2;
        g_bshuf_decompress_lz4 = bshuf_decompress_lz4_avx2;
    } else {
        g_bshuf_compress_lz4_bound = bshuf_compress_lz4_bound;
        g_bshuf_compress_lz4 = bshuf_compress_lz4;
        g_bshuf_decompress_lz4 = bshuf_decompress_lz4;
    }
#else
    g_bshuf_compress_lz4_bound = bshuf_compress_lz4_bound;
    g_bshuf_compress_lz4 = bshuf_compress_lz4;
    g_bshuf_decompress_lz4 = bshuf_decompress_lz4;
#endif
}

int64_t compress_lz4(void* in, void* out, size_t size, size_t elem_size, size_t block_size) {
    return g_bshuf_compress_lz4(in, out, size, elem_size, block_size);
}
int64_t decompress_lz4(void* in, void* out, size_t size, size_t elem_size, size_t block_size) {
    return g_bshuf_decompress_lz4(in, out, size, elem_size, block_size);
}
size_t compress_lz4_bound(size_t size, size_t elem_size, size_t block_size) {
    return g_bshuf_compress_lz4_bound(size, elem_size, block_size);
}

} // namespace bitshuffle
} // namespace doris
```
通过编译器参数`__attributed__((constructor))`实现程序加载时决定调用哪个 bitshuffle 版本。为了让 wrapper 能够区分 bitshuffle 版本，为特殊版本的函数名添加后缀 _avx2。由于未特殊版本的函数名添加了后缀，那么在链接时肯定是找不到该符号定义的，所以需要第二步，修改静态库中符号的名字。做法如下：
```sh
# bitshuffle
build_bitshuffle() {
    check_if_source_exist $BITSHUFFLE_SOURCE
    cd $TP_SOURCE_DIR/$BITSHUFFLE_SOURCE
    PREFIX=$TP_INSTALL_DIR

    # This library has significant optimizations when built with -mavx2. However,
    # we still need to support non-AVX2-capable hardware. So, we build it twice,
    # once with the flag and once without, and use some linker tricks to
    # suffix the AVX2 symbols with '_avx2'.
    arches="default avx2"
    MACHINE_TYPE=$(uname -m)
    # Becuase aarch64 don't support avx2, disable it.
    if [[ "${MACHINE_TYPE}" == "aarch64" ]]; then
        arches="default"
    fi

    to_link=""
    for arch in $arches ; do
        arch_flag=""
        if [ "$arch" == "avx2" ]; then
            arch_flag="-mavx2"
        fi
        tmp_obj=bitshuffle_${arch}_tmp.o
        dst_obj=bitshuffle_${arch}.o
        ${CC:-$DORIS_GCC_HOME/bin/gcc} $EXTRA_CFLAGS $arch_flag -std=c99 -I$PREFIX/include/lz4/ -O3 -DNDEBUG -fPIC -c \
            "src/bitshuffle_core.c" \
            "src/bitshuffle.c" \
            "src/iochain.c"
        # Merge the object files together to produce a combined .o file.
        $DORIS_BIN_UTILS/ld -r -o $tmp_obj bitshuffle_core.o bitshuffle.o iochain.o
        # For the AVX2 symbols, suffix them.
        if [ "$arch" == "avx2" ]; then
            # Create a mapping file with '<old_sym> <suffixed_sym>' on each line.
            $DORIS_BIN_UTILS/nm --defined-only --extern-only $tmp_obj | while read addr type sym ; do
              echo ${sym} ${sym}_${arch}
            done > renames.txt
            $DORIS_BIN_UTILS/objcopy --redefine-syms=renames.txt $tmp_obj $dst_obj
        else
            mv $tmp_obj $dst_obj
        fi  
        to_link="$to_link $dst_obj"
    done
    rm -f libbitshuffle.a
    $DORIS_BIN_UTILS/ar rs libbitshuffle.a $to_link
    mkdir -p $PREFIX/include/bitshuffle
    cp libbitshuffle.a $PREFIX/lib/
    cp $TP_SOURCE_DIR/$BITSHUFFLE_SOURCE/src/bitshuffle.h $PREFIX/include/bitshuffle/bitshuffle.h
    cp $TP_SOURCE_DIR/$BITSHUFFLE_SOURCE/src/bitshuffle_core.h $PREFIX/include/bitshuffle/bitshuffle_core.h
}
```
简单总结：
```bash
# 部分链接，将多个 .o 合并成一个 .o
ld -r -o $tmp_obj bitshuffle_core.o bitshuffle.o iochain.o
# 打印所有外部可链接的定义完成的符号：
nm --defined-only --extern-only {objfile}  
# 重命名
echo {sym} {sym}_suffix > rename.txt
# 重新生成新的重定位目标文件
objcopy --redefine-syms=rename.txt {objfile} new_objfile
```

## 情景二 开源库的不同版本有冲突
自己使用的开源库 bar 与项目中用到的开源库 foo 使用的 bar 不是同一个分支。
```c++
// bar1.cpp
#include <iostream>

void funcB() {
    std::cout << "bar1::funcB()\n";
}

// bar2.cpp
#include <iostream>

void funcB() {
    std::cout << "bar2::funcB()\n";
}

// foo.cpp
#include "bar1.h"

void funcA() {
    funcB();
}

// main.cpp
#include "foo.h"
#include "bar2.h"

int main() {
    funcA();
    funcB();
}
```
我们希望最终得到的可执行文件执行结果为：
```bash
bar1::funcB()
bar2::funcB()
```
### 方法一
分三步：

1. 将 bar1 和 foo 部分链接
```bash
[root@VM-211-238-centos makeLocal]# clang++ -c bar1.cpp
[root@VM-211-238-centos makeLocal]# clang++ -c foo.cpp

[root@VM-211-238-centos makeLocal]# readelf -s foo.o

Symbol table '.symtab' contains 5 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS foo.cpp
     2: 0000000000000000     0 SECTION LOCAL  DEFAULT    2
     3: 0000000000000000    11 FUNC    GLOBAL DEFAULT    2 _Z5funcAv
     4: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _Z5funcBv
```
进行 partial link
```bash
ld -r -o fooPartial.o 
```
部分链接后可以看到 foo 中的 funcB 已经找到了定义(readelf -s --wide 可以把 Name 的全写都打出来)
```bash
[root@VM-211-238-centos makeLocal]# readelf -s fooPartial.o

Symbol table '.symtab' contains 23 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 SECTION LOCAL  DEFAULT    1
     2: 0000000000000000     0 SECTION LOCAL  DEFAULT    3
     3: 0000000000000000     0 SECTION LOCAL  DEFAULT    5
     4: 0000000000000000     0 SECTION LOCAL  DEFAULT    6
     5: 0000000000000000     0 SECTION LOCAL  DEFAULT    8
     6: 0000000000000000     0 SECTION LOCAL  DEFAULT   10
     7: 0000000000000000     0 SECTION LOCAL  DEFAULT   11
     8: 0000000000000000     0 SECTION LOCAL  DEFAULT   12
     9: 0000000000000000     0 SECTION LOCAL  DEFAULT   13
    10: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS foo.cpp
    11: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS bar1.cpp
    12: 0000000000000040    11 FUNC    LOCAL  DEFAULT    3 _GLOBAL__sub_I_b[...]
    13: 0000000000000000     1 OBJECT  LOCAL  DEFAULT   10 _ZStL8__ioinit
    14: 0000000000000000    59 FUNC    LOCAL  DEFAULT    3 __cxx_global_var_init
    15: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZStlsISt11char_[...]
    16: 0000000000000000     0 NOTYPE  GLOBAL HIDDEN   UND __dso_handle
    17: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND __cxa_atexit
    18: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    19: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    20: 0000000000000010    31 FUNC    GLOBAL DEFAULT    1 _Z5funcBv
    21: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZSt4cout
    22: 0000000000000000    11 FUNC    GLOBAL DEFAULT    1 _Z5funcAv
```
2. Localize，将需要隐藏的符号类型改为LOCAL，防止全部链接时被外部引用链接到
```bash
[root@VM-211-238-centos makeLocal]# objcopy -L _Z5funcBv fooPartial.o fooPartialLocal.o
[root@VM-211-238-centos makeLocal]# readelf -s fooPartialLocal.o

Symbol table '.symtab' contains 23 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 SECTION LOCAL  DEFAULT    1
     2: 0000000000000000     0 SECTION LOCAL  DEFAULT    3
     3: 0000000000000000     0 SECTION LOCAL  DEFAULT    5
     4: 0000000000000000     0 SECTION LOCAL  DEFAULT    6
     5: 0000000000000000     0 SECTION LOCAL  DEFAULT    8
     6: 0000000000000000     0 SECTION LOCAL  DEFAULT   10
     7: 0000000000000000     0 SECTION LOCAL  DEFAULT   11
     8: 0000000000000000     0 SECTION LOCAL  DEFAULT   12
     9: 0000000000000000     0 SECTION LOCAL  DEFAULT   13
    10: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS foo.cpp
    11: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS bar1.cpp
    12: 0000000000000040    11 FUNC    LOCAL  DEFAULT    3 _GLOBAL__sub_I_b[...]
    13: 0000000000000000     1 OBJECT  LOCAL  DEFAULT   10 _ZStL8__ioinit
    14: 0000000000000000    59 FUNC    LOCAL  DEFAULT    3 __cxx_global_var_init
    15: 0000000000000010    31 FUNC    LOCAL  DEFAULT    1 _Z5funcBv
    16: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZStlsISt11char_[...]
    17: 0000000000000000     0 NOTYPE  GLOBAL HIDDEN   UND __dso_handle
    18: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND __cxa_atexit
    19: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    20: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    21: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZSt4cout
    22: 0000000000000000    11 FUNC    GLOBAL DEFAULT    1 _Z5funcAv
```
3. Full link
```bash
[root@VM-211-238-centos makeLocal]# clang++ -o main main.o fooPartialLocal.o bar2.o -lstdc++
[root@VM-211-238-centos makeLocal]# ./main
bar1::funcB()
bar2::funcB()
```

### 方法二

将 bar1 的 funcB 类型转为 LOCAL 还有另一个方法，在编译 bar1 时添加 `-fvisibility=hidden` 参数
```bash
[root@VM-211-238-centos makeFuncLocal]# clang++ -c bar1.cpp
[root@VM-211-238-centos makeFuncLocal]# readelf -s bar1.o

Symbol table '.symtab' contains 16 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS bar1.cpp
     2: 0000000000000040    11 FUNC    LOCAL  DEFAULT    4 _GLOBAL__sub_I_b[...]
     3: 0000000000000000     1 OBJECT  LOCAL  DEFAULT    6 _ZStL8__ioinit
     4: 0000000000000000    59 FUNC    LOCAL  DEFAULT    4 __cxx_global_var_init
     5: 0000000000000000     0 SECTION LOCAL  DEFAULT    2
     6: 0000000000000000     0 SECTION LOCAL  DEFAULT    4
     7: 0000000000000000     0 SECTION LOCAL  DEFAULT    6
     8: 0000000000000000     0 SECTION LOCAL  DEFAULT    7
     9: 0000000000000000    31 FUNC    GLOBAL DEFAULT    2 _Z5funcBv
    10: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    11: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    12: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZSt4cout
    13: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZStlsISt11char_[...]
    14: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND __cxa_atexit
    15: 0000000000000000     0 NOTYPE  GLOBAL HIDDEN   UND __dso_handle
[root@VM-211-238-centos makeFuncLocal]# clang++ -c bar1.cpp -fvisibility=hidden
[root@VM-211-238-centos makeFuncLocal]# readelf -s bar1.o

Symbol table '.symtab' contains 16 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS bar1.cpp
     2: 0000000000000040    11 FUNC    LOCAL  DEFAULT    4 _GLOBAL__sub_I_b[...]
     3: 0000000000000000     1 OBJECT  LOCAL  DEFAULT    6 _ZStL8__ioinit
     4: 0000000000000000    59 FUNC    LOCAL  DEFAULT    4 __cxx_global_var_init
     5: 0000000000000000     0 SECTION LOCAL  DEFAULT    2
     6: 0000000000000000     0 SECTION LOCAL  DEFAULT    4
     7: 0000000000000000     0 SECTION LOCAL  DEFAULT    6
     8: 0000000000000000     0 SECTION LOCAL  DEFAULT    7
     9: 0000000000000000    31 FUNC    GLOBAL HIDDEN     2 _Z5funcBv
    10: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    11: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZNSt8ios_base4I[...]
    12: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZSt4cout
    13: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND _ZStlsISt11char_[...]
    14: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND __cxa_atexit
    15: 0000000000000000     0 NOTYPE  GLOBAL HIDDEN   UND __dso_handle
```
`-fvisibility=hidden` 将 bar1 中的符号的 Vis 都设置为 HIDDEN，当 bar1.o 被链接为动态库时该符号类型将由 GLOBAL 转为 LOCAL
```bash
clang++ -shared foo.o bar1.o -o foo.so
readelf -s foo.so
    ...
    48: 0000000000001190    31 FUNC    LOCAL  DEFAULT   12 _Z5funcBv
    ...
    53: 0000000000001180    11 FUNC    GLOBAL DEFAULT   12 _Z5funcAv
    ...
```
最后链接动态库
```bash
clang++ main.cpp bar2.o -o main -lfoo
```
CMake demo
```cmake
cmake_minimum_required(VERSION 3.22)

project(MakeFuncLocal)

add_library(
    bar2 STATIC

    bar2.cpp
)

add_library(
    bar1 OBJECT

    bar1.cpp
)

target_compile_options(
    bar1 
    PRIVATE

    -fvisibility=hidden
)


add_library(
    foo SHARED

    foo.cpp
)

target_link_libraries(
    foo
    PRIVATE

    bar1
)

add_executable(
    main

    main.cpp
)

target_link_libraries(
    main

    bar2
    foo
)
```

### 方法三
使用 link-script，显示地告诉链接器，哪些符号在最终的动态库中可见，哪些不可见。[stackoverflow](https://stackoverflow.com/questions/8129782/version-script-and-hidden-visibility) 有关于该参数的解释。同样用我们的 demo 做一个例子。


创建一个内容如下的 export.txt
```txt
{
 global: *funcA*;
 local: *;
};
```
`man ld`查看 `--version-script` 参数的解释：

Specify the name of a version script to the linker.  This is typically used when creating shared libraries to specify additional information about the version hierarchy for the library being created.  This option is only fully supported on ELF platforms which support shared libraries; see VERSION.
It is partially supported on PE platforms, which can use version scripts to filter symbol visibility in auto-export mode: any symbols marked local in the version script will not be exported.

将该参数用于生成 libfoo.so
```bash
clang++ -Wl,--version-script=export.txt foo.cpp bar1.cpp -shared -o foo.so
```
检查一下 foo.so 的符号表：
```bash
readelf -s foo.so 

root@VM-211-238-centos makeFuncLocal]# readelf -s foo.so 

Symbol table '.dynsym' contains 11 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND 
     1: 0000000000000000     0 FUNC    WEAK   DEFAULT  UND [...]@GLIBC_2.2.5 (2)
     2: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND [...]@GLIBC_2.2.5 (2)
     3: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND [...]@GLIBCXX_3.4 (3)
     4: 0000000000000000     0 OBJECT  GLOBAL DEFAULT  UND [...]@GLIBCXX_3.4 (3)
     5: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND [...]@GLIBCXX_3.4 (3)
     6: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_deregisterT[...]
     7: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND __gmon_start__
     8: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_registerTMC[...]
     9: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND [...]@GLIBCXX_3.4 (3)
    10: 0000000000001180    11 FUNC    GLOBAL DEFAULT   12 _Z5funcAv

Symbol table '.symtab' contains 60 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
    ...
    48: 0000000000001190    31 FUNC    LOCAL  DEFAULT   12 _Z5funcBv
    ...
    53: 0000000000001180    11 FUNC    GLOBAL DEFAULT   12 _Z5funcAv
    ...
```
符合我们的要求。最终生成可执行目标文件
```bash
clang++ -o main main.cpp bar2.o foo.so
export LD_LIBRARY_PATH=.:$LD_LIBRARY_PATH
 ./main
bar1::funcB()
bar2::funcB()
```
CMake demo
```cmake
cmake_minimum_required(VERSION 3.22)

project(MakeFuncLocal)

add_library(
    bar2 STATIC

    bar2.cpp
)

add_library(
    bar1 STATIC

    bar1.cpp
)

target_compile_options(
    bar1
    PRIVATE

    -fPIC
)

add_library(
    foo SHARED

    foo.cpp
)

target_compile_options(
    foo
    PRIVATE

    -fPIC
)

target_link_libraries(
    foo
    PRIVATE

    bar1
)

target_link_options(
    foo
    PRIVATE

    -Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/export.txt
)

add_executable(
    main

    main.cpp
)

target_link_libraries(
    main

    bar2
    foo
)
```