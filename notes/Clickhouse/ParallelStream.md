# ClickHouse Part 写盘的 IO 模型

讲清楚一次 INSERT 把一个 part 写到存储介质上，数据在内存里怎么流、什么时候真正落盘 / 上传，以及为什么本地盘和对象存储（S3）的设计不一样。

## 0. 五层模型

从逻辑上把整条写路径分成五层，每层对应的真实类：

| 概念层 | 真实类 | 职责 |
|---|---|---|
| **Part 层** | `MergeTreeDataWriter::TemporaryPart`；sink 侧 `DelayedChunk` | 攒批、延迟 finalize、提交（ZK / part_log） |
| **PartStream** | `MergedBlockOutputStream` | 一个 part 一个，承载这个 part 的写出 |
| **ColumnWriter** | `IMergeTreeDataPartWriter`（`MergeTreeDataPartWriterWide` / `…Compact`）+ 内部 `column_streams` | 按 **PartFormat** 决定有几个列流 |
| **Buffer** | `MergeTreeDataPartWriterOnDisk::Stream` 缓冲链，链尾 `plain_file` | 每个列流各一份，互不共享 |
| **IO 层** | `WriteBufferFromFile`（本地）/ `WriteBufferFromS3`（对象存储） | 写 page cache / multipart 上传 |

数据流向：

```
INSERT block
  └─ Part 层  TemporaryPart  ──攒进──>  DelayedChunk ──finishDelayedChunk──> finalize+commit
       └─ PartStream  MergedBlockOutputStream
            └─ ColumnWriter  IMergeTreeDataPartWriter (Wide/Compact)
                 └─ column_streams[col] : Stream
                      compressed_hashing → compressor → plain_hashing → plain_file
                                                                        └─ Buffer / IO 层
                                                                           本地: WriteBufferFromFile → page cache
                                                                           S3:   WriteBufferFromS3   → multipart upload
```

---

## 1. 时序：一个 part 从创建到落盘（自上而下）

### 1.1 创建 PartStream，构造时建 ColumnWriter

`writeTempPartImpl` 准备好 part 元信息后，关键两步：先用 `choosePartFormat(size, rows)` 决定 **Wide 还是 Compact**，再创建 `MergedBlockOutputStream`：

```cpp
auto out = std::make_unique<MergedBlockOutputStream>(new_data_part, ...);
```

`MergedBlockOutputStream` 构造函数里按 part 类型创建 ColumnWriter：

```cpp
writer = createMergeTreeDataPartWriter(data_part->getType(), ...);   // Wide 或 Compact
```

**PartFormat 决定列流数**（ColumnWriter 构造时建好）：

- **Wide**（`MergeTreeDataPartWriterWide`）：构造里 `for (列) addStreams(...)`，**按 substream 一列一个 `Stream`**（`Nullable`/`Array`/`Nested`/`LowCardinality` 等会展开成多个子流）。`getNumberOfOpenStreams() == column_streams.size()`。
- **Compact**（`MergeTreeDataPartWriterCompact`）：所有列写进一个 `data.bin`，**只有 1 个流**。`getNumberOfOpenStreams() == 1`。

> 小 block 通常是 Compact（单流），大 block 是 Wide（多流）。

### 1.2 写数据：单线程逐列写入 Buffer

```cpp
out->writeWithPermutation(block, perm);   // → writer->write(block, perm)
```

`MergeTreeDataPartWriterWide::write` 是**单线程串行**的：

```cpp
for (列 in columns_list)            // 一列接一列
    writeColumn(列, ...);           // 内部再 for (granule) writeSingleGranule(...)
```

**同一时刻只有一列在被序列化**——不存在"多列多线程并行写"。N 个列流只是 N 份独立 Buffer，写它们的动作是串行的。数据经 `compressed_hashing→compressor→plain_hashing` 进到链尾 `plain_file` 的缓冲。

### 1.3 finalizePartAsync：只准备，不真正刷盘

```cpp
auto finalizer = out->finalizePartAsync(new_data_part, fsync_after_insert, ...);
```

它当下只做：`fillChecksums` + 写元信息文件（`columns.txt`/`checksums.txt`/`primary.idx`/`partition.dat`/`minmax_*` 等，但只 `preFinalize`），返回一个 `Finalizer`。**真正的 flush/sync/上传被推迟**。

> 注意命名：`writeTempPart` 返回时数据**并没写完**（`MergeTreeDataWriter.h` 注释：`You should call finalize() to wait until all data is written.`）。

### 1.4 回到 Part 层：攒批后才 finalize

sink 把写好的 `TemporaryPart` 攒进 `DelayedChunk`，到 `finishDelayedChunk` 才真正 finalize：

```cpp
// finishDelayedChunk
for (partition : delayed_chunk->partitions) {
    partition.temp_part.finalize();   // ★ 真正落盘/上传
    commitPart(...);                  // 提交 ZK / 记 part_log
}

// TemporaryPart::finalize → 每个 stream 的 Finalizer::finish()：
writer.finish(sync);                  // 关闭并刷各列流的 .bin/.mrk（S3：完成上传）
for (file : written_files) { file->finalize(); if (sync) file->sync(); }
```

至此数据才真正落到介质。**为什么要推迟到这里、为什么要攒批 → 见第 3 节**，而那又取决于 IO 层的介质特性 → 先看第 2 节。

---

## 2. Buffer → IO 层（从下往上：由介质特性决定设计）

这一层的形态完全由**存储介质**决定，所以从介质往上推。

### 2.1 Buffer 链结构（公共部分）

每个列流（`Stream`）持有一整条独立缓冲链：

```
compressed_hashing → compressor → plain_hashing → plain_file (WriteBufferFromFileBase)
```

- **每个列流各有一条，互不共享**；不同 part 也各有各的 writer/`column_streams`，写的是不同文件 / 不同 S3 对象。
- 区别只在链尾 `plain_file` 的具体类型。

### 2.2 本地盘：plain_file = WriteBufferFromFile → Page Cache

- `nextImpl()` 就是 `write(fd, ...)`，把数据交给 **OS page cache**；真正落盘是内核 writeback 异步做的（`fsync` 才强制）。
- **没有用户态攒批上传、没有后台上传线程**。
- 介质特性：瓶颈是单块物理设备，写/`fsync` 本质串行。同时开 N 个流"并行"写，并不能让一块盘更快，只是白占内存。
- ⇒ 所以本地盘**不需要**上层那套"攒多个流再批量 flush"的机制。

### 2.3 远程 parallel-io fs（S3/Azure）：plain_file = WriteBufferFromS3 → 专用内存 Buffer + 异步上传

- `WriteBufferFromS3` 维护**自己的用户态内存 buffer**；攒满一个分片阈值就把这块**交给共享线程池异步上传**，前台不等网络、继续写下一段（伪代码，提炼自 `WriteBufferFromS3.cpp`）：

```cpp
void WriteBufferFromS3::nextImpl() {            // 内存 buffer 满时触发
    detachBuffer();                             // 摘下已填满的 buffer
    if (累计 > max_single_part_upload_size)     // 32 MiB
        writeMultipartUpload();
    allocateBuffer();                           // 申请下一块（大小见 2.4）
}
void WriteBufferFromS3::writePart(PartData && data) {
    ++part_number;                              // 受 max_part_number=10000 硬限
    task_tracker->add([=]{ uploadPart(part_number, data); });  // ★ 后台线程池异步 UploadPart
    // 同一文件在飞分片数受 max_inflight_parts_for_one_file 约束
}
void WriteBufferFromS3::finalizeImpl() {
    if (没走 multipart && 数据 ≤ 阈值) makeSinglepartUpload();   // 小对象：一次 PutObject
    else completeMultipartUpload();             // 等所有在飞分片完成，再拼成对象
}
```

- 介质特性：单次上传**网络延迟高，但可堆并发**，吞吐随并发上升。
- **跨 part 的并发来自共享线程池**：所有 part / 所有列的 `WriteBufferFromS3` 把上传任务丢进同一个 object-storage writer 线程池。上层只要让**多个 part 的写缓冲同时存活**（即延迟 finalize），就能让它们的上传在池子里重叠。
- ⇒ 所以对象存储**需要**上层攒批/延迟，才能喂饱并发上传。

### 2.4 S3 分片大小：指数增长（ExpBufferAllocationPolicy）

分片不是固定大小（`BufferAllocationPolicy.cpp`，默认值 `S3Defines.h`）：

```cpp
// min_upload_part_size=16MiB(second), max_single_part_upload_size=32MiB(first),
// multiply_factor=2, multiply_parts_count_threshold=500, max_upload_part_size=5GiB, max_part_number=10000
size_t nextBuffer() {
    ++buffer_number;
    if (buffer_number == 1) return current = first_size;     // 32 MiB
    if (buffer_number == 2)        current = second_size;    // 16 MiB
    if ((buffer_number - 1) % multiply_threshold == 0)       // 每 500 片
        current = min(current * multiply_factor, max_size);  // ×2，封顶 5 GiB
    return current;
}
// 分片序列：32MiB, 16MiB×499, 32MiB×500, 64MiB×500, ... 直到 5GiB
```

目的：S3 单对象最多 10000 分片；固定 16MiB 只能撑 ~160GiB，指数增长让小对象用小分片（并发好、省内存），超大对象自动放大分片以不撞上限。

### 2.5 UploadPart 计数（Wide + S3）

每个列 `.bin` 是独立 S3 对象、独立 multipart upload。设该列**压缩后**落盘大小 `S`：

| `S`（压缩后） | 上传方式 | UploadPart 次数 |
|---|---|---|
| `≤ 32 MiB` | 单次 PutObject | **0** |
| 几十 MiB ~ 几 GiB（前 500 片内） | multipart，分片≈16MiB | **≈ S / 16MiB**（近似线性） |
| `> ~8 GiB`（超 500 片后） | multipart，分片翻倍 | **次线性** |

即：列越大（压缩后字节越多）→ UploadPart 越多，且按列独立；但看的是**压缩 on-disk 大小**，且分片大小会增长，故大对象转次线性。

### 2.6 小结

| 介质 | plain_file | Buffer 本质 | 后台上传 | 上层是否需要攒批 |
|---|---|---|---|---|
| 本地盘 | `WriteBufferFromFile` | OS page cache | 无（内核 writeback） | **否** |
| S3/Azure | `WriteBufferFromS3` | 用户态内存 buffer + 分片 | 有（共享线程池） | **是** |

**IO 层设计由介质特性反推，上层（Part 层）的攒批策略只是顺着 IO 层的需要而开关。**

---

## 3. 上层并行控制：为什么延迟 finalize（呼应第 2 节）

### 3.1 supportParallelWrite 看的是「盘的类型」，不是数量

```cpp
// IDisk.h            本地盘默认
virtual bool supportParallelWrite() const { return false; }
// S3ObjectStorage.h / AzureObjectStorage.h
bool supportParallelWrite() const override { return true; }
// DataPartStorageOnDiskBase  ← part 实际查它落在的那块盘
bool supportParallelWrite() const { return volume->getDisk()->supportParallelWrite(); }
```

### 3.2 攒批阈值逻辑

```cpp
if (settings.max_insert_delayed_streams_for_parallel_write.changed)
    max = settings_value;                              // 用户显式设
else if (support_parallel_write)                       // 该盘 supportParallelWrite()
    max = DEFAULT_DELAYED_STREAMS_FOR_PARALLEL_WRITE;  // = 1000
else
    max = 0;
...
// consume 循环里，按列级 open stream 数累加
current_streams = Σ stream->getNumberOfOpenStreams();
if (total_streams + current_streams > max)
    finishDelayedChunk();                              // 超阈值才提前 flush
```

### 3.3 三情景对比

| 情景 | `supportParallelWrite()` | `max` | 延迟 finalize | 并行体现在哪 |
|---|---|---|---|---|
| 单本地盘 | false | 0 | 关（写完即 finalize） | 无（单设备串行） |
| 多本地盘（JBOD） | false | 0 | 关（同单盘） | **不同 part 分散到不同物理盘**（选盘层，与本机制无关） |
| 远程 S3/Azure | true | 1000 | **开**（攒批、延迟 finalize） | **跨 part 的后台上传在共享线程池里重叠** |

注意：多块本地盘**不会**开启这套机制（每块盘仍 `false`）；它的并行是 `reserveSpacePreferringTTLRules` 把不同 part 分到不同盘，是另一条独立路径。

### 3.4 finishDelayedChunk 的攒批与流水线

- 本地盘（max=0）：每来一个新 part 就触发 flush，缓冲里最多滞留 1 个 part ⇒ 近似"写完即 finalize"，最后一个 part 在 `onFinish` 提交。
- S3（max=1000）：阈值很难触发，整轮 consume 的多个 part 全攒在一起，最后批量 finalize ⇒ 多 part 上传重叠。
- `finishDelayedChunk` 内对每个 part 顺序 `finalize()`（等其后台上传完）+ `commitPart`。延迟的意义就是让前面写 part 时启动的上传，在这里收尾时已大部分完成。

---

## 4. 一句话总结

ClickHouse 写 part 是 **Part → PartStream → ColumnWriter → Buffer → IO** 五层：`MergedBlockOutputStream` 按 PartFormat 建 `IMergeTreeDataPartWriter`（Wide 每列一流 / Compact 单流），**单线程逐列**把数据写进每个列流独立的 Buffer。Buffer→IO 层由介质决定——本地盘直接进 page cache（无后台并发，故不攒批），S3 用专用内存 buffer 攒满分片就交**共享线程池异步 multipart 上传**（有后台并发，故上层用 `delayed_chunk` + `max_insert_delayed_streams_for_parallel_write` **延迟 finalize、攒多个 part 让上传重叠**）。`supportParallelWrite()` 看盘的类型而非数量，因此只有对象存储才开启延迟 finalize。
