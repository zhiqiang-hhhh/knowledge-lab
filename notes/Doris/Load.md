Doris 导入流程提供的语意：一次导入完全成功或者完全失败。用事务 ID 来标记一次导入行为，用版本来维护每个 tablet 对用户可见的数据范围。
元数据是用来驱动可见性的载体，通过维护元数据列表来实现多版本控制。
元数据有哪些：
* Tablet 元数据: Tablet 上有哪些 rowset、哪些版本可见、哪些是 stale 状态（等待被回收）。
* Rowset 元数据: 一次生成的数据文件集合（segments）的描述信息，包含：版本、行数、大小、schema hash、生成时间、数据位置等。
* MOW 场景里还有 Delete Bitmap / Partial Update 信息：用来支撑 unique key merge-on-write 的可见性与一致性。


- 写入阶段（txn 进行中）

BE 接收数据，生成一组 segment 文件，形成一个“候选 rowset”。
这时候它的元数据处于 pending/非可见 状态：即使 BE 已经写出了数据文件，查询也不会读到它。
BE/FE 会记录“这个 txn_id 在哪些 tablets 上写了哪些东西”的跟踪信息（用于 commit/publish 时对齐）。
- Commit（单个BE执行成功）

单个 BE 完成某个 txn 的写入操作，添加元数据到 rocksdb，注意此时这批数据的版本号为 0，还不具备查询条件，版本号将会在 publish 的时候分配。FE 会收到各个 BE 的写入完成/提交信息，认为这批数据“已经具备发布条件”。

- Publish（真正让数据可见的元数据原子切换）

FE 下发 publish 任务到各个 BE：为每个 tablet 分配要发布的 version。
BE 做几个关键的元数据动作：
把 rowset 标记为 visible（绑定到目标 version）。
持久化 rowset_meta（以及 MOW 的 delete bitmap 等必要信息）。
更新 tablet 的版本视图：把“新版本”纳入可见集合。
清理 txn 跟踪信息。
这一步完成后，查询才会在版本线上“看到”这批数据。

- 失败与恢复语义

如果 publish 失败，Doris 依赖“持久化的元数据 + 可重试的 publish 协调”来保证最终一致：要么重试 publish 完成可见，要么超时/回滚清理 pending 数据。
关键点：可见性切换是由持久化元数据决定的，重启后依然能恢复到一致状态。

Doris 的“事务”（用户侧）本质是：把一批新数据作为整体发布成新的可见版本。
元数据管理围绕两件事展开：
* 写入阶段允许不稳定/可失败（pending，不影响查询）
* publish/切换阶段必须原子、可持久化、可恢复（决定可见性）
* compaction 虽然不是用户事务，但在元数据上同样遵循“先生成新 rowset → 再原子替换 → 旧的变 stale → 异步回收”

### 文件目录结构
```text
ShardId
    |
    TabletId
        |
        SchemaHash
            |
            RowSetId_SegmentId.dat
```
```cpp
Status DeltaWriter::write(const vectorized::Block* block, const DorisVector<uint32_t>& row_idxs) {
    if (UNLIKELY(row_idxs.empty())) {
        return Status::OK();
    }
    _lock_watch.start();
    std::lock_guard<std::mutex> l(_lock);
    _lock_watch.stop();
    if (!_is_init && !_is_cancelled) {
        RETURN_IF_ERROR(init());
    }
    {
        SCOPED_TIMER(_wait_flush_limit_timer);
        while (_memtable_writer->flush_running_count() >=
               config::memtable_flush_running_count_limit) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
    return _memtable_writer->write(block, row_idxs);
}
```
### Light Schema Change 与数据导入
```cpp
Status RowsetBuilder::init() {
    ...
    // build tablet schema in request level
    RETURN_IF_ERROR(_build_current_tablet_schema(_req.index_id, _req.table_schema_param.get(),
                                                 *_tablet->tablet_schema()));
    ...
}
```
`_build_current_tablet_schema`：Align the BE write schema with the FE-provided index schema for the current write, handling schema evolution, index selection, and partial-update configuration. It ensures the RowsetWriter writes data with the correct TabletSchema for a specific index_id.

```cpp
Status MemTableWriter::write(const vectorized::Block* block,
                             const DorisVector<uint32_t>& row_idxs) {
    auto st = _mem_table->insert(block, row_idxs);
    ...
    if (UNLIKELY(_mem_table->need_flush())) {
        RETURN_IF_ERROR(_flush_memtable());
    }
}
```
`MemTableWriter::_flush_memtable`实际上是提交了一个 MemtableFlushTask。执行 flush 动作：
```cpp
void FlushToken::_flush_memtable(std::shared_ptr<MemTable> memtable_ptr, int32_t segment_id,
                                 int64_t submit_task_time) {
    ...
    RETURN_IF_ERROR(_rowset_writer->flush_memtable(block.get(), segment_id, flush_size));
}
```
```cpp
Status BaseBetaRowsetWriter::flush_memtable(vectorized::Block* block, int32_t segment_id,
                                            int64_t* flush_size) {
    ...
    RETURN_IF_ERROR(_segment_creator.flush_single_block(block, segment_id, flush_size));
    ...
    return Status::OK();
}

Status SegmentFlusher::flush_single_block(const vectorized::Block* block, int32_t segment_id,
                                          int64_t* flush_size) {
    ...
    std::unique_ptr<segment_v2::VerticalSegmentWriter> writer;
    RETURN_IF_ERROR(_create_segment_writer(writer, segment_id, no_compression));
    RETURN_IF_ERROR_OR_CATCH_EXCEPTION(_add_rows(writer, &flush_block, 0, flush_block.rows()));
    RETURN_IF_ERROR(_flush_segment_writer(writer, flush_size));
}
```
`SegmentFlusher::_create_segment_writer()` 会使用创建 RowsetWriter 时候构造的 tablet schema 来决定某张表的 schema。
```cpp
Status SegmentFlusher::_create_segment_writer(
        std::unique_ptr<segment_v2::VerticalSegmentWriter>& writer, int32_t segment_id,
        bool no_compression) {
    io::FileWriterPtr segment_file_writer;
    RETURN_IF_ERROR(_context.file_writer_creator->create(segment_id, segment_file_writer));

    IndexFileWriterPtr index_file_writer;
    if (_context.tablet_schema->has_inverted_index() || _context.tablet_schema->has_ann_index()) {
        RETURN_IF_ERROR(_context.file_writer_creator->create(segment_id, &index_file_writer));
    }
}
```
### 数据流
```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  【发送端 BE】- Pipeline 执行线程 (PipelineTask 所在线程)                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  VTabletWriter::write()                                                             │
│       ↓                                                                             │
│  VNodeChannel::add_block() → 将 block 放入 _pending_blocks 队列                      │
│                                                                                     │
│  ═══════════════════════════════【线程切换 ①】═══════════════════════════════════════ │
│                               ↓                                                     │
│  _send_batch_thread (bthread)  ← periodic_send_batch() 独立 bthread 轮询            │
│       ↓                                                                             │
│  VNodeChannel::try_send_pending_block()                                             │
│       ↓                                                                             │
│  block.serialize() → PTabletWriterAddBlockRequest                                   │
│       ↓                                                                             │
│  _stub->tablet_writer_add_block(request)  ← brpc 异步调用                            │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │  【跨进程 RPC ★】
                                        │  brpc / HTTP
                                        ↓
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  【接收端 BE】- brpc IO 线程                                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  PInternalService::tablet_writer_add_block()  ← brpc worker 线程接收                 │
│       ↓                                                                             │
│  ═══════════════════════════════【线程切换 ②】═══════════════════════════════════════ │
│                               ↓                                                     │
│  _heavy_work_pool.try_offer([task]...)  ← 提交到 HeavyWorkPool 线程池               │
│       ↓                                                                             │
│  HeavyWorkPool 工作线程执行:                                                         │
│       ↓                                                                             │
│  LoadChannelMgr::add_batch()                                                        │
│       ↓                                                                             │
│  LoadChannel::add_batch()                                                           │
│       ↓                                                                             │
│  TabletsChannel::add_batch()                                                        │
│       │                                                                             │
│       ├── send_data.deserialize(request.block())  ← Block 反序列化                  │
│       │                                                                             │
│       └── _write_block_data()                                                       │
│               ↓                                                                     │
│           writer->write(&send_data, row_idxs)  ← 遍历每个 tablet                    │
│               ↓                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ DeltaWriter::write()                                                        │   │
│  │      ↓                                                                      │   │
│  │ MemTableWriter::write(block, row_idxs)                                      │   │
│  │      ↓                                                                      │   │
│  │ _mem_table->insert(block, row_idxs)  ★ 数据写入 MemTable                    │   │
│  │      ↓                                                                      │   │
│  │ _input_mutable_block.add_rows()  ← 行级别数据拷贝                            │   │
│  │      ↓                                                                      │   │
│  │ [如果 MemTable 满了]                                                        │   │
│  │      ↓                                                                      │   │
│  │ _flush_memtable_async()                                                     │   │
│  │      ↓                                                                      │   │
│  │ _flush_token->submit(memtable)                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                           │
│  ═══════════════════════════════【线程切换 ③】═══════════════════════════════════════ │
│                                        ↓                                           │
│  MemtableFlushPool 工作线程执行 (或 WorkloadGroup 的 flush pool):                    │
│       ↓                                                                            │
│  MemtableFlushTask::run()                                                          │
│       ↓                                                                            │
│  MemTable::flush() → Segment 文件写入磁盘                                           │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```




导入流程中涉及到一些数据结构的转换：
1. CSV -> Block
2. Block -> MemTable
3. MemTable -> Segment

ps: MemTable 这个对象实际上可以被消除（只有在导入的时候用到，实际查询/Compaction 的时候没有 MemTable 的概念）。

导入流程也是 Pipeline 的一部分，因此用户输入的 csv 格式首先会在接入的 BE 上转换成 Doris 查询引擎用到内存列式存储结构 Block。
Block 在算子之间流转，一直流动到 TableSink 算子。Doris 的数据模型是基于 Tablet 的，因此一个需要解决的问题是决定第 n 行应该属于哪一个 Tablet，这一步在 TableSink 算子的 Sink 步骤里完成。得到的结果是如下的数据结构
```cpp
struct Rows {
    int64_t partition_id;
    int64_t index_id;
    DorisVector<uint32_t> row_idxes;
};

using RowsForTablet = std::unordered_map<int64_t, Rows>;
```
RowsForTablet 配合 Block，就可以知道每一行与其对应的 Tablet 的映射关系。

MemTable -> Segment 的流程是在 MemTable 的 Flush 流程里完成的，这个转换有三个触发点：

1. **MemTable::need_flush() 触发** - 当 memtable 满时

在 memtable_writer.cpp#L140：
```cpp
if (UNLIKELY(_mem_table->need_flush())) {
    LOG_INFO("Going to flush memtable: tablet_id={}, memtable size: {}",
             _req.tablet_id, PrettyPrinter::print_bytes(_mem_table->memory_usage()));
    RETURN_IF_ERROR(_flush_memtable());
}
```
这是在每次 `write()` 写入数据后检查的，当 memtable 内存达到阈值时触发。

2. **数据消费完时触发** - 在 `close()` 时
在 memtable_writer.cpp#L246：
```cpp
Status MemTableWriter::close() {
    ...
    auto s = _flush_memtable_async();  // 强制 flush 剩余的 memtable
    {
        std::lock_guard<std::mutex> lm(_mem_table_ptr_lock);
        _mem_table.reset();
    }
    _is_closed = true;
    ...
}
```
当数据写入完成后调用 `close()`，会把当前 memtable（即使没满）也 flush 掉。

3. 第三个触发点：**全局内存压力触发** - 在 `MemTableMemoryLimiter::_flush_active_memtables()` 中，当系统内存压力大时，会主动 flush 一些 memtable 来释放内存。







#### MemTable
MemTable 的生成位置有两个可选的方案：
1. 在 TableSink 算子生成每一个 Tablet 的 MemTable，Flush 到当前 BE 后生成 Segment 文件，再通过网络把 Segment 文件发送到它应该属于的 BE 上。
2. 在 TableSink 算子得到 RowsForTablet 之后，通过网络把数据 shuffle 到对应的 BE，然后在对应的 BE 上生成 Segment。有副本的时，Segment 生成后还需要发送到相关的副本节点。

在 Local 部署模式下，Doris 默认采用的是第一种方式，而在 Cloud 模式下 Doris 采用的是第二种方式（注意 Cloud 模式没有副本，因此不需要 Segment 分发的逻辑）。


### Segment 文件的生成步骤
```text
// 第一阶段：写入数据到内存
for each input_row_batch {
    for each column {
        while (has_more_rows_in_batch) {
            append_rows_to_page_builder(rows)
            
            if (page_builder.is_page_full()) {
                // finish_current_page() 内部做以下操作：
                page_builder.finish()     // 编码当前 page
                compress_page_body()       // 压缩编码后的 page
                push_page_to_memory_list() // 将压缩页推入内存链表 _pages
                page_builder.reset()       // 重置 page builder
            }
        }
    }
    
    if (segment needs flush) {  // 行数达到 max_rows_per_segment 或大小达到限制
        goto flush_segment
    }
}

// 第二阶段：Segment 刷盘 (finalize)
flush_segment:
    // 1. finalize_columns_data()
    for each column_writer {
        column_writer.finish()    // 刷完最后一个未满的 page
    }
    
    for each column_writer {
        write_data_page // 遍历每个列的 page list，下刷到 segment 文件
    }
    
    // 2. finalize_columns_index()
    write_ordinal_index()         // 写 ordinal 索引
    write_zone_map()              // 写 zone map 索引
    write_inverted_index()        // 写倒排索引
    write_bloom_filter_index()    // 写布隆过滤器索引
    write_short_key_index()       // 写 short key 索引
    write_primary_key_index()     // 写主键索引 (MOW表)
    
    // 3. finalize_footer()
    write_segment_footer()        // 写 segment footer (元信息)
```

#### 不同 PageBuilder 的判断逻辑

| PageBuilder 类型 | 判断条件 | 说明 |
|-----------------|---------|------|
| **PlainPageBuilder** (定长类型) | `_remain_element_capacity == 0` | 按**元素个数**判断，`capacity = data_page_size / sizeof(type)` |
| **BitshufflePageBuilder** | `_remain_element_capacity == 0` | 同上 |
| **BinaryPlainPageBuilder** (变长类型) | `_size_estimate > data_page_size` | 按**字节大小**判断 |
| **RlePageBuilder** | `_rle_encoder.len() >= data_page_size` | 按压缩后**字节大小**判断 |

### 举例说明

假设 `data_page_size = 64KB`：

```
INT32 列:  capacity = 64KB / 4 = 16384 行后触发 page full
INT64 列:  capacity = 64KB / 8 = 8192 行后触发 page full  
STRING列:  取决于实际字符串大小，可能几百行就满了
```

每个列独立管理自己的 pages 链表（`std::vector<Page*> _pages`），最后在 `finalize()` 时统一写入磁盘。所以：
- **同一 segment 的所有列包含相同的行数**
- **但每个列的 page 数量和每个 page 的行数可能不同**