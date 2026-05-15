find_package(OpenMP REQUIRED)

add_executable(faiss_ivf_on_disk faiss_ivf_on_disk.cpp)
target_link_libraries(faiss_ivf_on_disk PRIVATE faiss OpenMP::OpenMP_CXX)

add_executable(my_ivf_on_disk my_ivf_on_disk.cpp)