
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [What is bitmaps](#what-is-bitmaps)
- [Why we use bitmaps](#why-we-use-bitmaps)
- [How to use bitmaps](#how-to-use-bitmaps)
- [Problems with Traditional bitmaps](#problems-with-traditional-bitmaps)
- [Roaring bitmaps](#roaring-bitmaps)

<!-- /code_chunk_output -->

## What is bitmaps
A more concise implementation of set.

A typical set is implemented in the form of hash tabler or RB-Tree or some other indexing data structure.

hash based:
```text
key -> hash(key) > hash_value

hash_value mod bucket to get bucket seq

check existence of hash_value in bucket[seq]
```
RB-Tree bases:
```text
key -> findLeaf(key) -> LeafNode
check existence of key in LeafNode
```
bitmaps offers almost same outside functionality with above structural, but in a different way and with a little different signature where it only accepts unsigned integer as its key type:
```text
container is a array of bit
check if container[key] equals to 1
```
## Why we use bitmaps
It is fast and space efficient in its usage situation.

For example, a bitmaps whose size is 8 bytes can store information of 8 * 8 = 64 users.
## How to use bitmaps

bitmaps is widely used in data science 


## Problems with Traditional bitmaps
## Roaring bitmaps