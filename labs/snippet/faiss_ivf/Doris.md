

以下是拆分后的三个时序图，分别覆盖 **写入（Build）**、**加载（Load）** 和 **搜索（Search）** 三个关键流程。

---

## 图 1：Build 阶段 — 写入两个文件

```mermaid
sequenceDiagram
    participant Writer as AnnIndexWriter
    participant IVF as IndexIVF<br/>(in-memory)
    participant Dir as Lucene Directory

    Note over Writer,Dir: Build: train + add 在内存中完成，save 时写两个文件

    Writer->>IVF: train(vectors) + add(vectors)
    Note over IVF: 内存中形成:<br/>① quantizer (nlist 个聚类中心)<br/>② ArrayInvertedLists (每个 list 的 codes + ids)

    Writer->>Dir: createOutput("ann.ivfdata")
    loop 对每个 list i = 0 .. nlist-1
        IVF-->>Dir: write codes[i]: list_size × code_size bytes
        IVF-->>Dir: write ids[i]: list_size × 8 bytes (idx_t)
    end
    Note over Dir: ann.ivfdata 写入完成

    Writer->>Dir: createOutput("ann.faiss")
    IVF-->>Dir: write index metadata<br/>(centroids, nlist, code_size, dim, metric, ...)
    Note over Dir: ann.faiss 写入完成
```

**ann.ivfdata 文件的 Binary 布局：**

```text
┌─────────── list 0 ──────────┬─────────── list 1 ──────────┬── ... ──┬─────── list N-1 ────────┐
│ codes (size×code_size bytes) │ codes (size×code_size bytes) │         │ codes                    │
│ ids   (size×8 bytes)         │ ids   (size×8 bytes)         │         │ ids                      │
└──────────────────────────────┴──────────────────────────────┴─────────┴──────────────────────────┘
```

**ann.faiss 文件：** 仅包含索引元数据（聚类中心向量、nlist、code_size、维度、距离类型等），**不包含倒排表数据**。

---

## 图 2：Load 阶段 — 只加载聚类中心到内存

```mermaid
sequenceDiagram
    participant Reader as AnnIndexReader
    participant Faiss as FaissVectorIndex
    participant Dir as Compound Directory
    participant Cache as AnnIndexIVFListCache<br/>(独立 LRU 缓存)

    Reader->>Dir: openInput("ann.faiss")
    Reader->>Faiss: read_index(SKIP_IVF_DATA)
    Note over Faiss: ✅ 加载到内存: 聚类中心 (quantizer)<br/>+ 每个 list 的 offset/size 元数据<br/>❌ 不加载: 倒排表向量数据

    Reader->>Dir: openInput("ann.ivfdata")
    Reader->>Faiss: 绑定 CachedRandomAccessReader<br/>(封装 ivfdata 文件句柄 + LRU Cache)

    Note over Faiss,Cache: 加载完成后的内存状态:<br/>• quantizer (nlist 个聚类中心) → 常驻内存<br/>• 每个 list 的 (offset, size) → 常驻内存<br/>• 倒排表向量数据 → 按需从磁盘读取，通过 LRU Cache 缓存
```

---

## 图 3：Search 阶段 — 粗量化 → 按 list 访问 → Cache / IO

```mermaid
sequenceDiagram
    participant Caller as 查询调用方
    participant Faiss as FaissVectorIndex
    participant Quantizer as Quantizer<br/>(聚类中心, 内存)
    participant V2 as OnDiskInvertedListsV2
    participant Cache as AnnIndexIVFListCache<br/>(LRU Cache)
    participant Disk as ivfdata 磁盘文件

    Caller->>Faiss: ann_topn_search(query_vec, k, nprobe)

    Note over Faiss,Quantizer: Step 1: 粗量化 — 找最近的聚类中心
    Faiss->>Quantizer: search(query_vec, nprobe)
    Quantizer-->>Faiss: 最近的 nprobe 个聚类 ID + 距离

    opt 开启 dynamic_nprobe
        Note over Faiss: SPANN 风格剪枝:<br/>按距离比率裁剪远处聚类<br/>actual_nprobe ≤ nprobe
    end

    Note over Faiss,Disk: Step 2: 逐 list 扫描倒排表
    loop 对每个被选中的聚类 list
        Faiss->>V2: get_iterator(list_no)

        Note over V2,Disk: 读取 codes 区域
        V2->>Cache: lookup(list_no codes offset)
        alt Cache 命中
            Cache-->>V2: 零拷贝返回 pinned 指针 ✅
        else Cache 未命中
            V2->>Disk: read(offset, size) 磁盘 IO
            Disk-->>V2: raw bytes
            V2->>Cache: insert → 缓存供后续查询复用
        end

        Note over V2,Disk: 读取 ids 区域 (同上 cache→disk 流程)
        V2->>Cache: lookup(list_no ids offset)
        alt Cache 命中
            Cache-->>V2: 零拷贝 ✅
        else Cache 未命中
            V2->>Disk: read(offset, size)
            V2->>Cache: insert
        end

        Note over Faiss: 遍历 list 中的每个向量:<br/>① IDSelector 过滤 (Roaring bitmap)<br/>② 计算 query 与向量的距离<br/>③ 维护 top-k 最小堆
    end

    Note over Faiss: Step 3: 返回结果
    Faiss-->>Caller: top-k 行 ID + 距离 (L2 做 sqrt 转换)
```

---

### 三图总结

| 阶段 | 核心行为 | 磁盘文件 | 内存占用 |
|------|---------|---------|---------|
| **Build** | train + add 后写出两个文件 | `ann.faiss` (元数据) + `ann.ivfdata` (倒排表) | 构建时全量，写完释放 |
| **Load** | 只读 centroids + list offset 元数据 | 读 `ann.faiss`，绑定 `ann.ivfdata` 文件句柄 | 极低（仅聚类中心） |
| **Search** | 粗量化 → 按 list 读数据（cache 优先）→ top-k | 按需读 `ann.ivfdata` 中对应 list | 热点 list 缓存在独立 LRU Cache |

## 关键流程说明

### 整体架构分三个阶段：

**Phase 1 — 索引加载（仅首次，`DorisCallOnce`）**
- ann_index_reader.cpp 打开 Compound 文件，通过 `faiss::read_index` 以 `IO_FLAG_SKIP_IVF_DATA` 标志**只读取元数据**（聚类中心向量/nlist/code_size），不加载倒排表数据
- 将 `OnDiskInvertedLists` 替换为 OnDiskInvertedListsV2.h（无 mmap、基于 `RandomAccessReader` 的读取方式）
- 创建 faiss_ann_index.cpp 绑定到 V2，它封装了 CLucene `IndexInput`（clone）并接入 ann_index_ivf_list_cache.h（独立 LRU 缓存）

**Phase 2 — 搜索（每次查询）**
1. **粗量化（Coarse Quantization）**：用内存中的 quantizer（`IndexFlat`）对 query_vec 搜索最近的 nprobe 个聚类中心
2. **动态 nprobe 剪枝**（可选，SPANN 风格）：通过 faiss_ann_index.cpp 根据距离比率裁剪不需要探测的聚类
3. **倒排表扫描**：对每个需要探测的聚类，OnDiskInvertedListsV2.cpp 通过 `borrow()` 一次性获取整个 list 的 codes 和 ids
4. **缓存机制**：`CachedRandomAccessReader::borrow()` 以精确 `(prefix, file_size, offset)` 为 key 查询 LRU cache，命中则**零拷贝**返回 pinned 指针；未命中则从磁盘读取后插入缓存
5. 在扫描过程中，FAISS 通过 `IDSelector`（封装 Roaring bitmap）过滤无效行，计算距离并维护 top-k 堆

**Phase 3 — 结果转换**
- 将 FAISS 返回的 `labels[]` 转换为 Roaring bitmap
- L2 距离做 `sqrt`（FAISS 返回的是平方距离）
- 收集 cache hit/miss 统计，写入 `AnnIndexStats` 和 `DorisMetrics`

### 核心设计亮点
- **内存占用极低**：只有聚类中心在内存中，倒排表数据全部 on-disk
- **缓存粒度与访问模式完美对齐**：每个 IVF list 的 codes 和 ids 各对应一个缓存条目，重复查询同一聚类时零拷贝命中
- **独立缓存池**：`AnnIndexIVFListCache` 与列数据/索引页缓存分离，容量可独立调优（默认物理内存 70%） 

Completed: *Draw sequence diagram* (3/3)