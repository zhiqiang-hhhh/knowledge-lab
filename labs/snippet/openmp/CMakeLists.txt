find_package(OpenMP REQUIRED)

add_executable(omp_multi_threads
    omp_multi_threads.cpp
)

target_link_libraries(omp_multi_threads
    PRIVATE
        OpenMP::OpenMP_CXX
)