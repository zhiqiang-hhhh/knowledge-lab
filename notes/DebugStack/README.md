add_custom_command 提示 `TARGET 'mytarget' was not created in this directory.`

https://stackoverflow.com/questions/40294146/alternative-to-cmake-post-build-command-when-target-is-in-subdirectory


连接器选项：

-Wl,--trace-symbol=<SYM> 对于只能打印 main 中的符号，不能打印出引用的其他库中的符号
--cref 可以把可执行文件里的所有符号，以及其在哪里被定义打印出来

https://stackoverflow.com/questions/55359700/trace-gcc-linker-linking-process

```
add_executable(main main.cpp)
target_link_libraries(main PRIVATE B)
target_link_options(main PUBLIC -Wl,--trace-symbol=main -Wl,--trace-symbol=FuncB2 -Wl,--Map=lmap -Wl,--cref)
```
链接器生成可执行文件时进行无用符号删除操作的粒度是编译单元，即可重定位目标文件。如果某个 .cc 中的符号没有被外部引用，那么这整个 .cc 将不会出现在最终的可执行目标文件中。

----

如果 library foo 对外暴露的头文件中用到了 library bar 的头文件，那么 library foo 的 CMakeLists 中一定需要把 library bar 的 link 可见性设置为 PUBLIC，
```
target_link_library(foo PUBLIC bar)
```
---
