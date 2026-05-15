ABI(application binary interface). The ABI is decided both by how the API and the compiler organize compiled code in the final object file. 

Every new release of g++ (for example, 4.2.0) is associated to a specific version of libstdc++ (for 4.2.0, version number is libstdc++.so.6.0.9). 


查看编译器的头文件搜索路径：
```bash
[hzq@VM-211-238-centos ~]$ cc -xc -E -v -
Using built-in specs.
COLLECT_GCC=/usr/bin/cc
OFFLOAD_TARGET_NAMES=nvptx-none
OFFLOAD_TARGET_DEFAULT=1
Target: x86_64-redhat-linux
Configured with: ../configure --enable-bootstrap --enable-languages=c,c++,fortran,lto --prefix=/usr --mandir=/usr/share/man --infodir=/usr/share/info --with-bugurl=http://bugzilla.redhat.com/bugzilla --enable-shared --enable-threads=posix --enable-checking=release --enable-multilib --with-system-zlib --enable-__cxa_atexit --disable-libunwind-exceptions --enable-gnu-unique-object --enable-linker-build-id --with-gcc-major-version-only --with-linker-hash-style=gnu --enable-plugin --enable-initfini-array --with-isl --disable-libmpx --enable-offload-targets=nvptx-none --without-cuda-driver --enable-gnu-indirect-function --enable-cet --with-tune=generic --with-arch_32=x86-64 --build=x86_64-redhat-linux
Thread model: posix
gcc version 8.5.0 20210514 (Red Hat 8.5.0-4) (GCC)
COLLECT_GCC_OPTIONS='-E' '-v' '-mtune=generic' '-march=x86-64'
 /usr/libexec/gcc/x86_64-redhat-linux/8/cc1 -E -quiet -v - -mtune=generic -march=x86-64
ignoring nonexistent directory "/usr/lib/gcc/x86_64-redhat-linux/8/include-fixed"
ignoring nonexistent directory "/usr/lib/gcc/x86_64-redhat-linux/8/../../../../x86_64-redhat-linux/include"
#include "..." search starts here:
#include <...> search starts here:
 /usr/lib/gcc/x86_64-redhat-linux/8/include
 /usr/local/include
 /usr/include
End of search list.
```