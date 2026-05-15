```plantuml
class AnnIndexColumnWriter {
    + init() : Status
    -  IndexFileWriter* _index_file_writer;
}

class IndexFileWriter {
    - InvertedIndexDirectoryMap _indices_dirs;
    - io::FileSystemSharedPtr _fs;
    - std::string _index_path_prefix;
    - std::string _rowset_id;
    - int64_t _seg_id;
    - InvertedIndexStorageFormatPB _storage_format;
    - std::string _tmp_dir;
    - const std::shared_ptr<io::LocalFileSystem>& _local_fs;
    - io::FileWriterPtr _idx_v2_writer
    IndexStorageFormatPtr _index_storage_format
}

class SegmentCreator {
    - SegmentFlusher _segment_flusher;
}

class SegmentFlusher {
    RowsetWriterContext& _context;
    SegmentFileCollection& _seg_files;
    InvertedIndexFileCollection& _idx_files;
}

```

```text
BetaRowsetWriterV2::flush_memtable()
|
|-SegmentFlusher::_flush_segment_writer
    |
    |-SegmentWriter::close_inverted_index()
        |
        |-IndexFileWriter::close()
```

```
SegmentFlusher::_flush_segment_writer
|
|-SegmentWriter::finalize
    |
    |-SegmentWriter::finalize_columns_index
        |
        |-SegmentWriter::_write_ann_index();
            |
            |-ArrayColumnWriter::write_ann_index()
                |
                |-AnnIndexColumnWriter->finish()
                    |
                    |-VectorIndex::save()
|
|-SegmentWriter::close_inverted_index()
    |
    |-IndexFileWriter::close()
```

```cpp
IndexFileWriter::close() {
    ...
    // Create compounded index file here.
    RETURN_IF_ERROR(_index_storage_format->write());

    for (const auto& entry : _indices_dirs) {
        const auto& dir = entry.second;
        // delete index path, which contains separated inverted index files
        if (std::strcmp(dir->getObjectName(), "DorisFSDirectory") == 0) {
            auto* compound_dir = static_cast<DorisFSDirectory*>(dir.get());
            compound_dir->deleteDirectory();
        }
    }
    ...
}
```
`IndexStorageFormatV2::write()` 会把当前 segment 对应的多个 tmp 目录下的索引文件打包压错成一个最终的 `.idx` 文件






```
zhiqiang-hhhh: I20250813 14:42:41.910436 3557178 faiss_vector_index.cpp:382] Faiss index saved to DorisRAMFSDirectory@/mnt/disk4/hezhiqiang/workspace/doris/cmaster/RELEASE/be1/storage/tmp/0200000000000001b34815d564ec81d95bed5cc408068b91_0_1755055107557, faiss.idx, rows 1, cost 0 ms
I20250813 14:42:41.910544 3557178 index_file_writer.cpp:225] IndexFileWriter closing, enable_write_index_searcher_cache: true
I20250813 14:42:41.910559 3557178 index_file_writer.cpp:122] IndexFileWriter::add_into_searcher_cache for /0200000000000001b34815d564ec81d95bed5cc408068b91_0
I20250813 14:42:41.910567 3557178 index_file_writer.cpp:125] IndexFileWriter::add_into_searcher_cache for /0200000000000001b34815d564ec81d95bed5cc408068b91_0
I20250813 14:42:41.910599 3557178 index_file_writer.cpp:127] IndexFileWriter::add_into_searcher_cache for /0200000000000001b34815d564ec81d95bed5cc408068b91_0, st: [E-6003]inverted index file /0200000000000001b34815d564ec81d95bed5cc408068b91_0.idx is not found.
I20250813 14:42:41.910611 3557178 index_file_writer.cpp:132] IndexFileWriter::add_into_searcher_cache for /0200000000000001b34815d564ec81d95bed5cc408068b91_0, no file found
I20250813 14:42:41.910619 3557178 segment_creator.cpp:248] tablet_id:1755055107539, flushing rowset_dir: , rowset_id:0200000000000001b34815d564ec81d95bed5cc408068b91, data size:526.00 B, index size:559

在什么情况下 index_file_writer会使用 StreamSinkFileWriter

GitHub Copilot: I'll scan the codebase to find where IndexFileWriter constructs a FileWriter and see the branch that returns a StreamSinkFileWriter, so I can state the exact conditions. I'll search for places where IndexFileWriter is constructed and where StreamSinkFileWriter is created, to identify the conditions leading to using it. I’ll pinpoint when IndexFileWriter is given a StreamSinkFileWriter and why your log shows “no file found”.

Checklist:
- Identify who constructs IndexFileWriter’s underlying FileWriter.
- Find the branch that returns StreamSinkFileWriter.
- Summarize the exact conditions and non-cases.

Answer:
- IndexFileWriter uses StreamSinkFileWriter when the write path is the stream-sink mode (i.e., using BetaRowsetWriterV2). In this path:
  - SegmentCreator asks RowsetWriter::create_index_file_writer(...).
  - That calls RowsetWriter::create_file_writer(..., FileType::INVERTED_INDEX_FILE).
  - In BetaRowsetWriterV2::create_file_writer, it always returns a StreamSinkFileWriter (initialized with load_id/partition/index/tablet/segment and file_type).
  - IndexFileWriter then receives this StreamSinkFileWriter as its _idx_v2_writer.

- This only applies for inverted index storage format V2+ (RowsetWriter only creates the idx file writer for V2; V1 doesn’t use _idx_v2_writer).

- Not used when writing locally via BaseBetaRowsetWriter (normal local files) or compaction/schema-change paths; those use LocalFileSystem/S3 writers.

- Your log line “IndexFileWriter::add_into_searcher_cache … not found file” is expected in this stream-sink case: data is streamed to replicas, so there’s no local idx file; IndexFileWriter explicitly treats “no file” as normal if _idx_v2_writer is a StreamSinkFileWriter.

zhiqiang-hhhh: 在cloud模式下会使用 S3FileWriter，这个逻辑在哪里实现的

GitHub Copilot: I’ll search the codebase to find S3FileWriter and trace where it’s instantiated and selected in “cloud” mode. 

zhiqiang-hhhh: @agent Try Again

GitHub Copilot: I’ll trace how “cloud mode” picks S3FileWriter and point you to the exact code paths.

Checklist
- Show where cloud mode switches to a remote FS (S3) for rowset writing.
- Show the call site that constructs S3FileWriter.
- Mention the alternate factory path when FileFactory is used.

Where the logic lives
- Cloud mode switches the writer to remote FS (S3)
  - cloud/cloud_rowset_writer.cpp: CloudRowsetWriter::init sets remote storage on the rowset and wires BaseBetaRowsetWriter machinery. It keeps RowsetWriterContext::storage_resource populated (cloud), so we don’t write to local FS.
  - olap/rowset/rowset_writer_context.h: RowsetWriterContext::fs() returns storage_resource->fs when is_local_rowset() == false (cloud). segment_path() also uses the remote path.
- The file writer creation funnels to S3FileWriter
  - beta_rowset_writer.cpp (BaseBetaRowsetWriter::_create_file_writer): calls _context.fs()->create_file(path, &file_writer, &opts). In cloud, fs() is an S3FileSystem.
  - io/fs/s3_file_system.cpp: S3FileSystem::create_file_impl constructs the concrete writer: *writer = std::make_unique<S3FileWriter>(...). This is the exact place S3FileWriter is chosen in cloud mode.
- Factory path (when creating writers via a generic factory)
  - io/file_factory.cpp: FileFactory::create_file_writer, case TFileType::FILE_S3, also returns std::make_unique<io::S3FileWriter>(...). Some flows use this factory directly.

Notes
- For inverted index V2 files, BaseBetaRowsetWriter::create_index_file_writer ultimately calls the same _create_file_writer path, so index files also use S3FileWriter in cloud.
- s3_obj_storage_client.cpp is used by S3FileWriter internally to talk to the object store; it’s not where the selection happens.

zhiqiang-hhhh: doris 里面的 memtbl 前移指的是什么

GitHub Copilot: Summarized conversation historyI'll scan key files to ground the “memtbl 前移” explanation in code: where the flag is set/checked and where the V2 sink and rowset writers are used. Then I’ll summarize findings and answer. I’ll ground “memtbl 前移” in this repo and point you to the exact flags, code paths, and effects.

## What “memtbl 前移” means

- Concept: Move memtable building/flushing from tablet replicas to the pipeline sink node (the BE running the sink operator), then stream the finished segment/index bytes to target replicas.
- Goal: Reduce network fan-out and per-replica build overhead; centralize write on sink then fan-out bytes via streams.

## When it’s used

- Sink selection: In pipeline_fragment_context.cpp, sink is switched to `OlapTableSinkV2OperatorX` only if:
  - `state->query_options().enable_memtable_on_sink_node` is true,
  - no inverted index V1 or partial update on the table,
  - and NOT in cloud mode.
  - See: `_create_data_sink(...)` case `TDataSinkType::OLAP_TABLE_SINK` (guard with `!config::is_cloud_mode()`).

- Writer path: With V2 sink enabled, BE uses `DeltaWriterV2` + `BetaRowsetWriterV2`, which create `StreamSinkFileWriter` for segments and inverted indexes.
  - beta_rowset_writer_v2.cpp: `create_file_writer(...)` builds `StreamSinkFileWriter`.
  - `be/src/io/fs/stream_sink_file_writer.*`: streams data to peers; no local files.

- Index v2 support: Enabled by context flag:
  - rowset_writer_context.h: `bool memtable_on_sink_support_index_v2`.
  - Set true in delta_writer_v2.cpp so inverted index V2 bytes are also streamed.

## How to enable/propagate

- Session variable (SQL): `set enable_memtable_on_sink_node = true`.
  - Tests/examples in regression suite show usage.
- Stream load HTTP header: `memtable_on_sink_node: true`
  - Parsed in stream_load.cpp and http_common.h.
- Routine load: Thrift field propagated to BE in routine_load_task_executor.cpp.

## What you’ll observe

- No local segment/index files at the sink; bytes go over streams.
- `IndexFileWriter` detects streaming and treats “file not found” as normal:
  - index_file_writer.cpp checks `dynamic_cast<StreamSinkFileWriter*>` and skips local lookup/logging accordingly.

## Limitations and guards

- Not in cloud mode: In cloud, Doris uses the FS path (e.g., S3) instead of memtable-on-sink V2; the code explicitly disables V2 sink when `config::is_cloud_mode()` is true.
- Not with inverted index V1 or partial update (guarded in the same sink selection branch).

## Benefits and trade-offs

- Pros: Less network fan-out, shared delta writers (see comments in `be/src/common/config.{h,cpp}`), higher throughput on wide replication.
- Cons: Higher memory pressure at the sink; requires index V2 compatibility; different failure/retry surface at stream layer.

If you want, I can trace a specific load/query to show whether it took the V2 sink path and where the streams were opened.
```




zhiqiang-hhhh: _get_row_ranges_by_keys 的输入是一组 key_range，输出是过滤之后的 key_rangea，我想知道主键索引具体是怎么工作的，包括：
1. key_range 跟从哪里得到的哪个数据结构做对比？

GitHub Copilot: I'll quickly scan the related primary key and short key index code paths to ground the explanation in the actual implementation and confirm which structures are used during lookup. 

Searched text for `primary_key_index|PrimaryKeyIndex|_lookup_ordinal_from_pk_index|short_key_index|ShortKeyIndex|_lookup_ordinal_from_sk_index|_seek_and_peek|RowCursor|KeyRange` (`**/be/src/**`), 20 results

Read [](file:///mnt/disk4/hezhiqiang/code/doris/be/src/olap/rowset/segment_v2/segment_iterator.cpp#1495-1495), lines 1495 to 1615

Read [](file:///mnt/disk4/hezhiqiang/code/doris/be/src/olap/rowset/segment_v2/segment_iterator.cpp#1420-1420), lines 1420 to 1540

我先结合这段代码路径，解释 key_range 在“主键索引”查找里到底跟哪个数据结构对比，以及比对流程。

- key_range 的来源
  - 在 `SegmentIterator::_get_row_ranges_by_keys()` 里使用的是 `_opts.key_ranges`（来自 StorageReadOptions，通常由上层 TabletReader/Scan 运算根据查询条件构造）。
  - 每个 `key_range` 含有 `lower_key/upper_key`（`RowCursor`），以及是否包含边界的标志 `include_lower/include_upper`。

- 实际对比的数据结构（主键索引场景）
  - 当表是 UNIQUE_KEYS，且这个 segment 携带主键索引时（`_segment->get_primary_key_index() != nullptr`），`_lookup_ordinal()` 会走主键索引路径：`_lookup_ordinal_from_pk_index()`。
  - 这里对比的是“本 segment 的主键索引文件中的有序索引列”（IndexedColumn）：
    - 通过 `PrimaryKeyIndexReader` 拿到一个 `IndexedColumnIterator`：
      - `const PrimaryKeyIndexReader* pk = _segment->get_primary_key_index();`
      - `pk->new_iterator(&index_iterator, _opts.stats);`
    - 把 `RowCursor` 边界 key 编码成与索引一致的字节串（包含/不包含的处理会反映在编码上）：
      - `encode_key_with_padding<RowCursor, true>(&index_key, key, num_key_columns, is_include);`
    - 先和 segment 的元数据边界做一次剪枝：
      - 如果 `index_key < _segment->min_key()` -> rowid = 0
      - 如果 `index_key > _segment->max_key()` -> rowid = num_rows()
    - 核心对比：用 `IndexedColumnIterator::seek_at_or_after(&index_key, &exact_match)` 在主键索引里做 lower_bound 查找，得到当前位置的 ordinal（即 segment 内的行号）：
      - `*rowid = index_iterator->get_current_ordinal();`
    - 如果表有 sequence 列，主键索引里存的是“主键+sequence”的全键。为判断是否真“命中”，会读出索引里的该条 key，去掉 sequence 的尾部字节后与查询 key 再比一次，以修正 `exact_match`。
    - 如果是上界且不包含（`!include_upper`），并且是 exact_match，则把 rowid 再往后移 1（取“第一个大于上界”的位置）。

- 非主键索引的回退（补充）
  - 若不是 UNIQUE_KEYS 或该 segment 没有 PK 索引，则用短键索引 `ShortKeyIndexDecoder`：
    - `lower_bound/upper_bound` 先锁定一个 block 粗范围，再在数据上通过 `_seek_and_peek(mid)` 做二分比较，精确定位 ordinal。

- 代码锚点（便于对照）
  - `SegmentIterator::_get_row_ranges_by_keys()`：循环 `_opts.key_ranges`，对上下界分别调用 `_lookup_ordinal(...)` 计算 rowid，再合并为行区间。
  - `SegmentIterator::_lookup_ordinal()`：判断 UNIQUE_KEYS+PK 索引则走 `_lookup_ordinal_from_pk_index()`，否则走 `_lookup_ordinal_from_sk_index()`。
  - `SegmentIterator::_lookup_ordinal_from_pk_index()`：主键编码、与 `min_key()/max_key()` 比较、`seek_at_or_after()` 查找、sequence 列处理、边界包含性处理。
  - 这些都在当前文件 segment_iterator.cpp 中。

一句话总结
- key_range 的边界 key 会被编码成“与主键索引同格式的字节串”，先与 segment 的 `min_key()/max_key()` 快速比较，再用 `PrimaryKeyIndexReader` 提供的 `IndexedColumnIterator::seek_at_or_after` 在“主键索引的有序索引列（IndexedColumn）”中做定位，对比结果就是这个定位逻辑返回的位置（ordinal/rowid）。

zhiqiang-hhhh: 当主键索引有多个的时候，pk index 是怎么执行的

GitHub Copilot: 你问的“主键索引有多个”有两种常见理解，我把两种都说明白：

1) 多个“主键列”（复合主键）的情况
- Doris 在每个 segment 内只有一个主键索引结构，但它是“复合键”的单一有序索引。实现上把多个主键列按列序拼接成一个按字典序可比较的字节串，然后在一个有序的 IndexedColumn 里存储、查找。
- 入口在 `SegmentIterator::_lookup_ordinal_from_pk_index`：
  - 用 `encode_key_with_padding<RowCursor, true>(&index_key, key, num_key_columns, is_include)` 把 RowCursor（可能是前缀 key）编码成索引用的字节串。多个主键列就是连续编码，保序。对于上/下界与是否包含（include_upper/include_lower），这个编码会相应调整（例如上界不包含时要找第一个大于上界的位置）。
  - 先用 segment 粗粒度边界 `_segment->min_key()/max_key()` 快速剪枝。
  - 再用 `PrimaryKeyIndexReader::new_iterator()` 拿到 `IndexedColumnIterator`，调用 `seek_at_or_after(&index_key, &exact_match)` 做 lower_bound 查找，返回当前位置的 ordinal（行号）。
  - 如果表有 sequence 列，主键索引里存的是“主键列拼接 + sequence”完整键。为了正确处理 exact_match 和边界包含性，代码会在 `!exact_match` 且 `has_seq_col` 时读出当前索引键，去掉末尾 sequence 字节后再和查询 key 比较一次，必要时修正 exact_match。若 exact_match 且是“不包含”边界，则 `rowid += 1`，保证取到“第一个大于边界”的行。
- 小结：复合主键不是“多个独立 pk 索引”，而是“一个按复合键编码的有序索引”。对比只发生在这一条索引上，不会逐列索引分别比。

2) “多个主键索引文件”的情况（跨多个 segment/rowset）
- 每个 segment 有自己的主键索引。扫描时每个 `SegmentIterator` 只对自己 segment 的 pk 索引做上/下界寻位，得到该 segment 内的 `[lower_rowid, upper_rowid)`。`_get_row_ranges_by_keys()` 会对传入的多个 key_range 循环做上面这套寻位，然后把得到的行区间 union 起来，再与其它 bitmap/inverted/zonemap/delete bitmap 等过滤结果做交集。
- 跨多个 segment 的合并由更高一层（如 TabletReader/执行器）协调，`SegmentIterator` 只负责本段。

补充要点
- 如果是 UNIQUE_KEYS 且存在 cluster key（见代码中的 DCHECK 注释），获取 key range 不走 pk 索引而是回退到 short key 索引路径（`_lookup_ordinal_from_sk_index`），因为这类表的范围定位需要 short key 粒度。
- 多个 key_range 会在 `_get_row_ranges_by_keys()` 里逐个计算边界 rowid，然后对行区间做 union。
- 查找复杂度基本是每个边界一次 `seek_at_or_after` 的 O(log N)，序列列校正最多多读一条索引值做一次字节比较，代价很小。

关联代码位置（便于你对照）
- 复合主键编码与查找：segment_iterator.cpp 中
  - `_lookup_ordinal()`：判断是否走 pk 索引
  - `_lookup_ordinal_from_pk_index()`：主流程，min/max 剪枝、`encode_key_with_padding`、`seek_at_or_after`、sequence 校正、边界包含处理
- 多 key_range 的处理：`_get_row_ranges_by_keys()` 循环 union 行区间

如果你具体关心“前缀范围”（比如只给复合键的前几列）怎么编码，或 sequence 列的确切编码长度（见 `sequence_col_idx().length() + 1`），也可以继续问，我再结合编码细节展开。

zhiqiang-hhhh: 因此如果有多个主键的话，为了让主键索引生效那么查询的谓词必须满足一些规则？

GitHub Copilot: 是的。对“多列主键（复合主键）”要想触发主键索引（PK index）范围裁剪，谓词需要能被规划器转换成可编码的“复合键字典序区间”。结合当前实现，满足这些规则更容易生效：

- 表与存储前提
  - 表类型为 UNIQUE_KEYS，且该 segment 存在主键索引（`_segment->get_primary_key_index()!=nullptr`）。
  - 不是 Z-ORDER 排序，且没有 cluster key（代码里对 cluster key 会改走短键索引，见注释）。
  - 本次扫描的读 schema 中至少包含一个主键列；否则 `_get_row_ranges_by_keys()` 会直接跳过。

- 谓词形态必须能生成“复合键前缀区间”
  - 主键列按定义的顺序组成复合键，字典序排序。要形成一个连续 key range，通常需要：
    - 对若干“前导主键列”是等值约束（k1=…, k2=…，…），
    - 对“最后一个出现的主键列”允许是范围约束（>, >=, <, <=, BETWEEN），
    - 不允许在某个主键列上出现范围后，再对后续主键列设条件（那样无法形成单一连续区间）。
  - 只约束前缀也可以（例如仅 k1 的范围，或 k1=常量 且 k2 的范围）。
  - IN/OR 一般不会直接变成一个区间，但规划器可能把 OR/IN 展开成多段等值/范围，从而生成多条 KeyRange 再取并集；是否展开取决于上层规则。
  - LIKE、函数、表达式（非常量）的谓词不会用于生成 key ranges；需要能折叠成常量的等值/范围才行。

- 类型与编码一致性
  - 条件值需与主键列类型兼容；编码时调用 `encode_key_with_padding<RowCursor, true>` 生成与索引一致的字节序列（注意上/下界包含性的处理）。
  - 若表有 sequence 列：PK 索引里保存的是“主键拼接 + sequence”。查询无需在谓词里涉及 sequence，代码会在命中位置读取索引键并“去掉 sequence”再次比对以确认 exact_match，然后按是否包含上/下界微调 rowid。

- 其它注意点
  - `key_ranges` 必须非空；它由上层根据上述谓词形态生成。若只在非键列上过滤，就不会有 key range，自然不会走 PK 索引裁剪。
  - 多个 key_range 会在 `SegmentIterator::_get_row_ranges_by_keys()` 里逐个定位上下界 rowid，再做并集后与其他过滤（bitmap/inverted/zonemap/delete bitmap 等）相交。

一句话总结：复合主键要用上 PK 索引，谓词需要能被转成“按主键顺序的前缀等值 + 末列范围”的字典序区间；只要能生成对应的 key_range，Segment 侧就会用主键索引的 `seek_at_or_after` 做上下界定位并裁剪行范围。

zhiqiang-hhhh: 主键为 A，B，C，查询条件是 B=b,C=c，此时主键索引如何工作

GitHub Copilot: 结论先说：主键为 (A, B, C) 且只有 B=b、C=c 的条件时，这条查询通常无法利用主键索引做范围裁剪。原因是 Doris 的主键索引按复合键的字典序排序，必须从“最左前缀”开始约束，才能把匹配键映射为一个（或若干个）连续区间去用 seek 做上/下界定位。

具体说明如下：
- 排序与连续性
  - 主键索引按 (A, B, C) 进行字典序排序。想用索引做范围裁剪，需要把谓词转成“连续的复合键区间”。
  - 只限定 B=b、C=c 而不限定 A 时，满足条件的键是集合 {(A=?, b, c) | A 为所有可能值}。在按 A 作为第一排序键的顺序下，这些点会被与其它 (A, B, C) 值交错，无法形成一个连续区间，也就没法用一次 seek_at_or_after 定位出 [lower_rowid, upper_rowid)。
  - 只有当前导列（A）被等值或范围约束时，才有可能形成连续区间：例如
    - A=a 且 B=b, C=c（精确点）
    - A=a 且 B=b 且 C 在某范围（一个小区间）
    - A 在某范围，B、C 不设置（一个大区间）
    - A=a 且 B 在某范围，C 不设置（一个中等区间）
  - 一旦在某个主键列使用了范围，后续的主键列一般不能再继续约束（否则也不再是单一连续区间），需要上层拆成多个区间。

- 代码层面怎么体现
  - 生成 key range 的职责在上层（Planner/TabletReader）；`SegmentIterator::_get_row_ranges_by_keys()` 只消费 `_opts.key_ranges`。如果没有基于“最左前缀”的谓词，上层通常不会生成 key_range，这里就直接跳过。
  - 真正做定位时，`_lookup_ordinal_from_pk_index()` 会把“边界键”编码成与索引一致的字节串，并用 `IndexedColumnIterator::seek_at_or_after` 找上下界。但前提是边界键可构造且对应一个连续区间；B、C-only 在语义上无法构造出有效区间，因此这条路径不会被触发。
  - sequence 列（`has_seq_col`）仅影响“命中位置是否 exact_match 以及不包含边界时 rowid 是否 +1”的微调，不改变“必须从最左前缀约束”的基本规则。

- 这类查询实际会发生什么
  - 不走主键索引裁剪；`_get_row_ranges_by_keys()` 不作处理。
  - 后续会依次尝试其他过滤手段：bitmap index、倒排索引（若在 B/C 上建了）、BloomFilter、zone map、delete bitmap 等；最后再按谓词做列级过滤。

- 如何让它用到索引
  - 谓词中增加对 A 的等值或范围限制，使之成为从最左前缀起的“等值前缀 + 最后一列范围”的形式。
  - 调整主键列顺序，把查询中更常作为筛选条件的列放到前面。
  - 在 B/C 上建立合适的倒排索引（如 BKD/全文）或 bitmap，以便在没有 A 约束时也能下推到存储层过滤。

一句话：主键索引是“最左前缀友好”的顺序索引。只有从 A 开始的前缀谓词（等值为主，末列可范围）才能把匹配集变成连续区间，从而用 seek 做范围裁剪；仅有 B=b、C=c 时不会触发 PK 索引裁剪。

zhiqiang-hhhh: 一旦在某个主键列使用了范围，后续的主键列一般不能再继续约束（否则也不再是单一连续区间），需要上层拆成多个区间。

这句话怎么理解？给我个例子说明

GitHub Copilot: 好的，这里用复合主键 (A, B, C) 的字典序来直观说明“某一列一旦用了范围，后面的列就不能再继续约束，否则需要拆成多个区间”的含义，并配几个具体例子。

核心规则
- 索引顺序是按 (A, B, C) 的字典序。
- 能形成单个连续区间的谓词形态必须是“前导列全等值 + 最后一列允许范围”，后面不再约束。
  - 例如 A=常量、B=常量、C∈[c1,c2] 是一个连续区间。
  - 一旦某列是范围（比如 B 是范围），则后面的列（C）若再约束，就会把匹配集切成多个不相邻的小片段，无法用“一个区间”概括，只能拆分成多个区间求并。

为什么会这样？
- 因为字典序里，A 是最外层分组，其次是 B，再是 C。某层用范围时，这一层不同取值之间会插入很多其他取值的块，导致“跨层”的选择集合不是连续的一整段。

例子 1：A 是范围，B 有等值
- 谓词：A ∈ [1, 3] 且 B = 5（C 不限）
- 在字典序中，满足集合是三个不相邻的块：
  - (A=1, B=5, C=−∞…+∞)
  - (A=2, B=5, C=−∞…+∞)
  - (A=3, B=5, C=−∞…+∞)
- 这三段中间夹着 (A=1, B≠5, …)、(A=2, B≠5, …) 等数据，整体不是单个连续区间。
- 上层必须拆分为多个 KeyRange，并取并集：
  - [ (1,5,−∞), (1,5,+∞) )
  - [ (2,5,−∞), (2,5,+∞) )
  - [ (3,5,−∞), (3,5,+∞) )

例子 2：A 等值，B 是范围，C 不约束（允许）
- 谓词：A = 1 且 B ∈ [10, 20]（C 不限）
- 这是单个连续区间：[(1,10,−∞), (1,20,+∞))
- 因为“前导列 A 等值 + 最后一列 B 范围”，后面 C 不再约束，符合“单区间”条件。

例子 3：A 等值，B 是范围，C 还有等值（不再是单区间）
- 谓词：A = 1 且 B ∈ [10, 12] 且 C = 7
- 字典序下，匹配点是
  - (1,10,7)、(1,11,7)、(1,12,7)
- 但在 (1,10,7) 与 (1,11,7) 之间，字典序里还存在 (1,10,>7) 的很多键；因此这三点并不构成一段连续区间。
- 必须拆分为三段（每个 B 一段）：
  - [ (1,10,7), (1,10,7) ]、[ (1,11,7), (1,11,7) ]、[ (1,12,7), (1,12,7) ]

例子 4：只约束 B、C（没有 A 前缀）
- 谓词：B = b 且 C = c
- 因为最左前缀 A 未约束，满足集合是 {(A=*, b, c)}，按 (A,B,C) 排序会与大量其他键交错，不能形成单个区间，通常也不会生成任何 key_range（这类查询不会用 PK 索引裁剪）。

和实现如何对上
- 在 Doris 的实现里，`SegmentIterator::_get_row_ranges_by_keys()` 只是消费上层生成的 `key_ranges`。能否用一个 KeyRange 表达，取决于谓词能否用上述“前缀等值 + 末列范围”的形式表示为单个连续区间。
- 若出现“中间某列用范围，后面列继续约束”的形态，上层应按照“固定前缀逐个枚举”的方式拆成多个区间（如上例 1 和 3 的拆分），然后在段内用 `_lookup_ordinal_from_pk_index()` 分别做上/下界 seek，最后把行区间做并集。

一句话
- 想用主键索引做一次 seek 的连续裁剪，谓词必须能转成“最左前缀等值 + 最后一个列范围、后面不再约束”。一旦在某列用了范围而后面还加条件，就只能拆成多个小区间让存储层分别定位。

zhiqiang-hhhh: 如果是多个范围的话，为什么不能走pk index呢？

GitHub Copilot: Summarized conversation history你问“多个范围为什么不能走 PK index？”我先给结论：不是一概不能。能不能走，取决于这些“多个范围”能否被表达成少量按主键字典序连续的区间，并且满足主键的左前缀规则；否则要么表达不出来要么代价太高，Doris 就会放弃用 PK 索引。

要点如下：
- PK 索引是按复合主键的字典序（含 seq 列在索引里的末尾字节）有序的。它最擅长的是“单个连续区间”的查找：下界 seek_at_or_after 一次、上界再 seek 一次，就得到 [lo, hi) 的 rowid 区间。
- Doris 的实现确实支持“多个区间”：Scan 侧会把可用的谓词转成多个 KeyRange 放进 `_opts.key_ranges`，`_get_row_ranges_by_keys()` 会逐个 range 用 `_lookup_ordinal_from_pk_index()` 去定位边界，然后把这些区间 union 成最终行集。所以“多个范围”如果本身就是“少量连续区间”，是可以走 PK 索引的。
- 不能（或不划算）走 PK 索引的“多范围”主要有两类：
  1) 不满足左前缀等值的复合主键谓词。比如 PK(A,B,C)，只有 B in (...) 或 B,C 的条件，没有 A=…。这些条件在字典序上会分散到无数位置，无法用“少量连续区间”覆盖；要精确表达，需要对每一个可能的 A 拆成很多小区间，数量不可控，seek 次数爆炸，代价远大于扫描/二级索引。
  2) 在某一主键列已经是范围的基础上，又对后续主键列加等值/列表等进一步约束。这样的结果通常是许多不相邻的小片段，而不是一个或少量连续区间；需要拆成大量 KeyRange 才能用 PK 索引，同样会造成大量随机 seek，反而更慢。通常这时会退到短键索引/bitmap/inverted/zonemap/BF 等路径。
- 还有一些明确不走 PK 索引的场景限制：
  - 表是 ZORDER 排序或是 cluster key（代码里有 DCHECK，cluster key 取范围用短键索引而不是 PK 索引）。
  - 不是 UNIQUE_KEYS（或没有 segment 级 PK 索引）就会走短键索引路径。
  - 计划器侧对 KeyRange 数量有上限/启发式，超过阈值会放弃用 PK 索引。

两个小例子帮你区分“可用/不可用”：
- 可用（多个但少量连续区间）：PK(A,B,C)，谓词是 A in (1,3) 且 B ∈ [10,20]。它等价于两段连续区间：
  - [ (1,10,-inf), (1,20,+inf) ) ∪ [ (3,10,-inf), (3,20,+inf) )
  扫描会生成两个 KeyRange，分别对 PK 索引做两次下/上界 seek。
- 不可用/不划算：PK(A,B,C)，谓词是 B in (5,7)，A 未指定。按主键字典序，这会在所有 A 的分区里反复出现，想要精确表达必须为每个可能的 A 生成两段区间，总数可能巨大，seek 开销不可接受，于是不会走 PK 索引。

补充实现细节（对应你标出的 has_seq_col 处）：PK 索引键里包含了序列列的字节，`_lookup_ordinal_from_pk_index()` 先用全键 seek，再在 has_seq_col 时把序列列长度扣掉比对“无序列列”的部分来判断 exact_match，并在非包含上界时做 +1 调整。这个流程天然是“一个边界一次 seek”，也说明了多段离散小区间会导致大量 seek。

总结：当“多个范围”是少量、按主键字典序连续的区间，并且满足左前缀等值+最后一列范围的模式时，会走 PK 索引；当“多个范围”来自于不满足左前缀或“范围后再加后续列约束”导致结果碎片化时，就不能（或不该）走 PK 索引，系统会选择更合适的索引或扫描路径。