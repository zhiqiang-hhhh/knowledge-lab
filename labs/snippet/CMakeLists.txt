cmake_minimum_required(VERSION 3.22)
project(Snippet VERSION 1.0.0)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Use C++17 for std::filesystem and other modern APIs.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 设置编译优化级别为 O3
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
set(CMAKE_C_FLAGS_RELEASE "-O3 -DNDEBUG")

# 如果没有指定构建类型，默认使用 Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

option(WITH_VECML "Enable building VecML components" OFF)

add_subdirectory(integrate_faiss)
add_subdirectory(csapp)
add_subdirectory(openmp)
if(WITH_VECML)
    add_subdirectory(vecml)
endif()
add_subdirectory(snippets_of_snippets)
