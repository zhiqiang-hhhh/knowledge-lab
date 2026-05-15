```bash
[root@VM-211-238-centos /data/demo]# tree .
.
├── CMakeLists.txt
├── foo2
│   ├── CMakeLists.txt
│   ├── foo
│   │   ├── CMakeLists.txt
│   │   ├── foo.cc
│   │   └── foo.h
│   ├── foo2.cc
│   └── foo2.h
└── main.cpp 
```

### CMAKE_BUILD_TYPE
```shell
# Nothing == empty string
c++ -I/data/demo/foo2 -I/data/demo/foo2/foo -o main.cpp.o -c /data/demo/main.cpp
# RelWithDebInfo
c++ -I/data/demo/foo2 -I/data/demo/foo2/foo -O2 -g -DNDEBUG -o main.cpp.o -c /data/demo/main.cpp
# Release
c++ -I/data/demo/foo2 -I/data/demo/foo2/foo -O3 -DNDEBUG -o main.cpp.o -c /data/demo/main.cpp
# Debug
c++ -I/data/demo/foo2 -I/data/demo/foo2/foo -g -o main.cpp.o -c /data/demo/main.cpp
```
对于gcc而言，它的[默认优化级别](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)是 -O0

如果 CMAKE_BUILD_TYPE 为空，且父CMake中设置了 CMAKE_BUILD_TYPE，则继承父CMake。
### 编译参数与cmake声明顺序的关系
```bash
[root@VM-211-238-centos /data/demo]# tree .
.
├── CMakeLists.txt  // target_compile_options(main PRIVATE -Wall -O3 -g)
├── foo2
│   ├── CMakeLists.txt  // target_compile_options(foo2 PUBLIC -O2)
│   ├── foo
│   │   ├── CMakeLists.txt  // target_compile_options(foo PUBLIC -O0)
│   │   ├── foo.cc
│   │   └── foo.h
│   ├── foo2.cc
│   └── foo2.h
└── main.cpp 
```


各个编译单元的编译参数（modified）：
```shell
# foo
c++ -g -O0 -o foo.cc.o -c foo2/foo/foo.cc

# foo2
c++ -I/data/demo/foo2/foo -g -O2 -O0 -o foo2.cc.o -c /data/demo/foo2/foo2.cc

# foo3
c++ -I/data/demo/foo2 -I/data/demo/foo2/foo -O3 -DNDEBUG -O3 -g -O2 -O0 -o main.cpp.o -c /data/demo/main.cpp
```
这里说明CMake是先续遍历的方式处理compile_options的。