`sh build.sh --be`

180 行，这里`${DORIS_HOME}`是执行

在 `build_Release` 目录下执行
```bash
cmake   -G Unix_MakeFile 
        -DDORIS_HOME=... 
        -DCMAKE_BUILD_TYPE=... 
        ... 
        -DPROTOBUF_PROTOC_EXECUTABLE=${DORIS_HOME}/thirdparty/installed/bin/protoc
        -DDORIS_BUILD_DIR=${CMAKE_BUILD_DIR}/doris_be/
        -DDORIS_INSTALL_PREFIX=${CMAKE_BUILD_DIR}/output/
        ${DORIS_HOME}/contrib/clickhouse 
```
也就是说，我们这里项目的 root CMakeLists.txt 用到的是`${DORIS_HOME}/contrib/clickhouse`包含的CMakeList.txt 


CC 与 CXX 都是 CMake 使用的环境变量。前者用于指定编译 .c 的编译器，后者用于指定编译 .cxx 的编译器。

```
${CMAKE_CMD} -G "${GENERATOR}" -DDORIS_HOME=${DORIS_HOME} -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} -DMAKE_TEST=OFF -DWITH_MYSQL=${WITH_MYSQL} -DWITH_LZO=${WITH_LZO} -DBUILD_TESTING=OFF -Dgperftools_enable_stacktrace_via_backtrace=ON -DWITH_OPENSSL=OFF -DUSE_AMQPCPP=OFF -DLLVM_ENABLE_LIBCXX=ON -DORC_CXX_HAS_UNIQUE_PTR=ON -DEVENT__DISABLE_MBEDTLS=ON -DEVENT__LIBRARY_TYPE=STATIC -DEVENT__DISABLE_OPENSSL=ON -DEVENT__DISABLE_SAMPLES=ON -DLEVELDB_BUILD_TESTS=OFF -DLEVELDB_BUILD_BENCHMARKS=OFF -DBUILD_WITH_TOLAP=ON -DPROTOBUF_PROTOC_EXECUTABLE=${DORIS_HOME}/thirdparty/installed/bin/protoc  -DDORIS_BUILD_DIR=${CMAKE_BUILD_DIR}/doris_be/ -DCMAKE_INSTALL_PREFIX=${DORIS_HOME}/output/  ${DORIS_HOME}/contrib/clickhouse 
```