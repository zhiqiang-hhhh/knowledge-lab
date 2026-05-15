# IVF + mmap Prototype

This prototype demonstrates:
- IVF reduces compute by scanning only `nprobe` inverted lists.
- `mmap` keeps vectors on disk and reads only probed list ranges.

## C++ version (no Python dependency)

Build:

```bash
clang++ -O2 -std=c++17 ivf_mmap_proto/prototype.cpp -o ivf_mmap_proto/prototype
```

Run:

```bash
./ivf_mmap_proto/prototype --nprobe 4
./ivf_mmap_proto/prototype --nprobe 16
```

You should observe:
- `avg_recall@k` increases with larger `nprobe`
- `avg_candidates` and estimated bytes read per query also increase

That is exactly the IVF + mmap tradeoff in practice.

## Build Index Diagrams

### 1) In-memory layout during `build_index`

```text
Input:
  xb (float32, N * D)
  row i => xb[i*D ... (i+1)*D-1]

Step A: train coarse centroids
  centroids (float32, nlist * D)
  centroid c => centroids[c*D ... (c+1)*D-1]

Step B: assign each vector to nearest centroid
  list_id (int32, N)
  list_id[i] = nearest centroid id of xb[i]

Step C: reorder by list_id
  order (int32, N) = argsort(list_id, stable=true)

Step D: list boundaries
  counts  (uint64, nlist)
  offsets (uint64, nlist+1)
  list lid range => [offsets[lid], offsets[lid+1])

Step E: materialize sorted payload
  xb_sorted  (float32, N * D)
  ids_sorted (int32, N)

  for pos in [0..N):
    src = order[pos]
    xb_sorted[pos] = xb[src]
    ids_sorted[pos] = src
```

### 2) On-disk file layout after `build_index`

```text
workdir/
  vectors.f32     float32[N * D]
  ids.i32         int32[N]
  offsets.u64     uint64[nlist + 1]
  centroids.f32   float32[nlist * D]
```

```text
vectors.f32 and ids.i32 are aligned by "pos":

  pos:      0          ...        offsets[1]-1 | offsets[1] ... offsets[2]-1 | ...
            |---------------- list 0 ----------------------| |------ list 1 ------|

  vectors: [v_sorted_0][v_sorted_1]...[v_sorted_pos]...
  ids:     [orig_id_0 ][orig_id_1 ]...[orig_id_pos ]...

For a list `lid`:
  start = offsets[lid]
  end   = offsets[lid + 1]
  scan positions [start, end)
```

### 3) Query-time mapping (logical list -> mmap range)

```text
coarse select nprobe list ids
    lid in probe_set
      -> use offsets to get [start, end)
      -> read vectors/ids only in this range via mmap-backed pointer
```

## Python version

`prototype.py` is also included, but it requires `numpy`.

## Faiss-Like OnDiskIVF Prototype

File:
- `ivf_mmap_proto/faiss_like_ondisk_ivf.cpp`

This version is closer to Faiss architecture:
- Coarse quantizer (kmeans centroids)
- Encoded inverted-list payload (`id + code`)
- One-file on-disk index with list directory
- mmap-backed list scanning at query time

### Build and run

```bash
clang++ -O2 -std=c++17 ivf_mmap_proto/faiss_like_ondisk_ivf.cpp -o ivf_mmap_proto/faiss_like_ondisk_ivf
./ivf_mmap_proto/faiss_like_ondisk_ivf --nprobe 4
./ivf_mmap_proto/faiss_like_ondisk_ivf --nprobe 16
```

### Component mapping to Faiss concepts

```text
This prototype                  ~ Faiss concept
-------------------------------------------------------------
centroids                        coarse quantizer
SQ8Codec                         vector codec (like SQ/PQ family)
ListDirEntry[]                   inverted-list directory (offset, size)
list payload: [id][code]...      per-list codes + ids
search_ivf_sq8()                 IVF search over probed lists
mmap_ro() + load_index_from_mmap on-disk inverted lists access
```

### Single-file format

```text
[DiskHeader]
[centroids: float32(nlist*d)]
[codec vmin: float32(d)]
[codec invgap: float32(d)]
[list directory: ListDirEntry(nlist)]
[list payload area]

List payload for each list:
  repeated `size` times:
    [id: int64][code: uint8[code_size]]
```

### Faiss reading map (from this prototype to Faiss source mental model)

```text
Prototype function / struct           -> Faiss concept / typical class
---------------------------------------------------------------------------
train_kmeans()                        -> coarse quantizer training
                                        (IndexIVF quantizer training path)

SQ8Codec::train/encode                -> codec training + encode
                                        (IndexScalarQuantizer / IndexPQ family)

build_inverted_lists()                -> add() 阶段把向量分桶并写入 list
                                        (IndexIVF::add_with_ids + InvertedLists)

ListDirEntry(offset,size)             -> list directory metadata
                                        (OnDiskInvertedLists list offsets/sizes)

write_index_file()                    -> serialize index metadata + lists
                                        (write_index / IO writer stack)

mmap_ro() + load_index_from_mmap()    -> load on-disk lists by mmap
                                        (OnDiskInvertedLists mapped file)

search_ivf_sq8()                      -> search pipeline:
                                        1) quantizer search -> nprobe lists
                                        2) scan selected lists
                                        3) maintain top-k heap/result handler
                                        (IndexIVF::search + scanner)
```

### Search pipeline alignment with Faiss

```text
Query q
  -> coarse distances to centroids
  -> pick nprobe list ids
  -> for each list id:
       locate [offset,size] in directory
       iterate entries [id|code]
       compute distance(q, decoded(code))
  -> merge all candidates
  -> select top-k
```

### What is still simplified vs Faiss

```text
1) codec is SQ8-only (Faiss supports richer codecs, optimized LUT paths, etc.)
2) single-threaded scan (Faiss has extensive parallel/search optimizations)
3) no residual/PQ-ADC style fast distance tables
4) simplified I/O format and lifecycle management
5) no delete/update, no advanced prefetch/cache strategies
```
