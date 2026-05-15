
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Order of evaluation](#order-of-evaluation)

<!-- /code_chunk_output -->


# Vectorization

Do poeraitons on all elements of a vector simultaneously. This is also called Single-Instruction-Multiple-Data (SIMD) operations.

The total size of each vector can be 64 bits (MMX), 128 bits (XMM), 256 bits (YMM), and 512 bits (ZMM).

The vector operations use a set of special vector registers. 
Max size of vector register:
* 128 bit if SSE2 instruction set is available
* 256 bit if AVX instruction set is supported
* 512 bit if AVX512 is available