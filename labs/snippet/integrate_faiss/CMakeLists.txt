# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# Make sure compile check in doris will not break compilation of faiss and openblas
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -w")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -w")

set(BUILD_WITHOUT_LAPACK OFF CACHE BOOL "Disable LAPACK support in OpenBLAS")
set(NO_SHARED TRUE CACHE BOOL "Disable shared library in OpenBLAS")
set(C_LAPACK TRUE CACHE BOOL "Enable C interface for LAPACK in OpenBLAS")
set(USE_OPENMP TRUE CACHE BOOL "Enable OpenMP in OpenBLAS")
set(NOFORTRAN ON CACHE BOOL "Disable Fortran in OpenBLAS")
set(BUILD_STATIC_LIBS ON CACHE BOOL "Build static libraries in OpenBLAS")
set(BUILD_TESTING OFF CACHE BOOL "Build shared libraries in OpenBLAS")
set(BUILD_RELAPACK ON CACHE BOOL "Build relapack in OpenBLAS")
set(BUILD_BENCHMARKS OFF CACHE BOOL "Build benchmarks in OpenBLAS")
set(NO_LAPACK OFF CACHE BOOL "Disable LAPACK in OpenBLAS")
set(NO_CBLAS ON CACHE BOOL "Disable CBLAS in OpenBLAS")
set(NO_AVX512 ON CACHE BOOL "Disable AVX512 in OpenBLAS")

# EXCLUDE_FROM_ALL so that binary in openblas is not installed.
add_subdirectory(${PROJECT_SOURCE_DIR}/contrib/openblas ${PROJECT_BINARY_DIR}/openblas EXCLUDE_FROM_ALL)

set(OPENBLAS_LIBRARY "${PROJECT_BINARY_DIR}/openblas/lib/libopenblas.a" CACHE PATH "Path to OpenBLAS build directory")
set(FAISS_ENABLE_MKL OFF CACHE BOOL "Disable MKL support in FAISS")
set(FAISS_ENABLE_GPU OFF CACHE BOOL "Disable GPU support in FAISS")
set(FAISS_ENABLE_PYTHON OFF CACHE BOOL "Disable Python support in FAISS")
set(FAISS_ENABLE_EXTRAS OFF CACHE BOOL "Disable FAISS extras")
set(BUILD_TESTING OFF CACHE BOOL "Disable FAISS testing")

# EXCLUDE_FROM_ALL so that binary in faiss is not installed.
add_subdirectory(${PROJECT_SOURCE_DIR}/contrib/faiss ${PROJECT_BINARY_DIR}/faiss EXCLUDE_FROM_ALL)

find_package(Threads REQUIRED)
find_package(OpenMP REQUIRED COMPONENTS C CXX)

add_executable(integrate_faiss main.cpp)
target_link_libraries(integrate_faiss PRIVATE faiss OpenMP::OpenMP_CXX)

add_executable(faiss_analysis src/faiss_analysis.cpp util/cli_utils.cpp util/results_utils.cpp)
target_link_libraries(faiss_analysis PRIVATE faiss Threads::Threads OpenMP::OpenMP_CXX)

# VecML (Fluffy) support: optional C shim to avoid C++ ABI conflicts
option(VECML_LIB_PATH "Path to VecML SDK dir containing fluffy_interface.h and libfluffy_shared_lib.so" "")
option(VECML_USE_OLD_CXX_ABI "Build vecml_shim with the old libstdc++ ABI to match VecML SDK" ON)

if(WITH_VECML)
	if(VECML_LIB_PATH)
		set(VECML_INCLUDE_DIR "${VECML_LIB_PATH}" CACHE PATH "VecML include dir")
		set(FLUFFY_LIBRARY "${VECML_LIB_PATH}/libfluffy_shared_lib.so" CACHE FILEPATH "VecML shared lib")
		set(CPR_LIBRARY "${VECML_LIB_PATH}/libcpr.so.1" CACHE FILEPATH "libcpr dependency for VecML")
	endif()

	if(VECML_INCLUDE_DIR AND FLUFFY_LIBRARY AND CPR_LIBRARY)
		message(STATUS "VecML detected: include=${VECML_INCLUDE_DIR}, fluffy=${FLUFFY_LIBRARY}, cpr=${CPR_LIBRARY}")
		add_library(vecml_shim SHARED vecml_shim/vecml_shim.cpp)
		target_include_directories(vecml_shim PRIVATE ${VECML_INCLUDE_DIR} ${PROJECT_SOURCE_DIR}/integrate_faiss)
		target_link_libraries(vecml_shim PRIVATE ${FLUFFY_LIBRARY} ${CPR_LIBRARY})
		if(VECML_USE_OLD_CXX_ABI)
			target_compile_definitions(vecml_shim PRIVATE _GLIBCXX_USE_CXX11_ABI=0)
		endif()
		# expose HAVE_VECML to faiss_analysis compilation when VecML is available
		target_compile_definitions(faiss_analysis PRIVATE HAVE_VECML=1)
		target_link_libraries(faiss_analysis PRIVATE vecml_shim)
	else()
		message(STATUS "VecML support requested (WITH_VECML=ON) but required SDK libraries were not found; building faiss_analysis without VecML.")
	endif()
else()
	message(STATUS "WITH_VECML=OFF, building faiss_analysis without VecML support.")
endif()
