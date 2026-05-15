
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [MemoryMappings](#memorymappings)
  - [Overview](#overview)

<!-- /code_chunk_output -->


# MemoryMappings
## Overview

`mmap` creates a new memory mapping in the calling process's virtual address space.

* File mapping: Map contents of a file to the corresponding memory region of calling process.
* Anonymous mapping: Shareing same physical memory.

mapping memory can be shared between multiple processes.

* Two processes map the same region of a file, they share the same pages of physical memory.
A child process created by folk() inherits copies of its parent's mappings, and these mappings refre to the same pages of physical memory.

Shared type of mapping controls whether modifications can be shared between processes.

* Private mapping(`MAP_PRIVATE`): Changes to the contents are private to each process. System kernel accomplishes this by using the copy-on-write technique.
* Shared mapping(`MAP_SHARED`): Share the modification.

So there are four different types of mmap:
* Private file mapping: Some common examples are initializing a process’s text and initialized data segments from the corresponding parts of a binary executable file or a shared library file.
* Private anonymous mapping: The primary purpose of private anonymous mappings is to allocate new (zero-filled) memory for a process (e.g., malloc() employs mmap() for this purpose when allocating large blocks of memory).
* Shared file mapping: 会把一个文件的内容加载到进程内存中的指定区域，对这段内存区域的修改都会被写回到文件中。因此 shared file mapping 提供了一种对于文件 read/write 替代操作。另一个用途是允许不相关的进程去共享内存空间来进行一种更快的IPC操作。
* Shared anonymous mapping: 为相关（有继承关系）进程提供一种 IPC 方式。POSIX shared memory objects 可以与 mmap 一起为不相关进程提供类似的 IPC 方式。






