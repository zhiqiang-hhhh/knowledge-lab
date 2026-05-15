[TOC]

# StorageMergeTree
## 目录组织
<center>
<img alt="picture 1" src="../../images/b54750afebc9e83dd903f9da36c39d1138725a13dc91009d656d09fc58a838e1.png" height="600px" width="700px"/>  
</center>

path 是 config.xml 中的 path 字段指定的路径。该路径下保存所有的 meta 以及 data。

### MergeTreeBlockOutputStream::write
分析一个函数 MergeTreeBlockOutputStream::write(const Block & block)

数据样本：
```sql
CREATE TABLE test_table(key Int64, value Int64, devider Int64) ENGINE=MergeTree ORDER BY key PARTITION BY devider

INSERT INTO TABLE test_table VALUES (100, 10000, 1),(101, 10001, 2),(102, 10002, 3),(103, 10003, 4),(104, 10004, 1)
```

对于我们的输入样本，实参的 block 将会长这样（抽象）：
<center>
<img alt="picture 1" src="../../images/04713b06ef3615613f1674442a1b68809a3002fa85d1a81387ce288d14c75589.png"
height="300px" width="" />
</center>
```c++
auto part_blocks = storage.writer.splitBlockIntoParts(block, max_parts_per_block, metadata_snapshot);
```
part_blocks 是一个数组，每个元素是一个 partition + block 的组合，按照我们的输入一共有 4 个不同的 partition，因此 part_blocks 将会包含 4 个元素
<center>
<img alt="picture 4" src="../../images/c0ca9d6e013a7d1aefa32037e419af45587f6a84b80fef1887d001da89ac9aac.png"
height="300px" width="" />
</center>

下一步动作是循环将每个 partitionAndBlock 写入磁盘。单就一次写入来说，有多少个 partition 就会产生多少个 part 文件。
```c++
for (auto & current_block : part_blocks)
{
    Stopwatch watch;

    MergeTreeData::MutableDataPartPtr part = storage.writer.writeTempPart(current_block, metadata_snapshot, optimize_on_insert);

    /// If optimize_on_insert setting is true, current_block could become empty after merge
    /// and we didn't create part.
    if (!part)
        continue;

    /// Part can be deduplicated, so increment counters and add to part log only if it's really added
    if (storage.renameTempPartAndAdd(part, &storage.increment, nullptr, storage.getDeduplicationLog()))
    {
        PartLog::addNewPart(storage.getContext(), part, watch.elapsed());

        /// Initiate async merge - it will be done if it's good time for merge and if there are space in 'background_pool'.
        storage.background_executor.triggerTask();
    }
}
```
写入动作分为两步，首先`writeTempPart`创建目录`temp_insert_1_1_1_0`，然后`renameTempPartAndAdd`将其重命名为`1_1_1_0`，并将其加入内存。

#### StorageMergeTree::MergeTreeDataWriter::writeTempPart
```c++
MergeTreeData::MutableDataPartPtr MergeTreeDataWriter::writeTempPart(
    BlockWithPartition & block_with_partition, const StorageMetadataPtr & metadata_snapshot, ContextPtr context)
{
    static const String TMP_PREFIX = "tmp_insert_";

    /// This will generate unique name in scope of current server process.
    Int64 temp_index = data.insert_increment.get(); // A
    
    ...
    
    MergeTreePartInfo new_part_info(partition.getID(metadata_snapshot->getPartitionKey().sample_block), temp_index, temp_index, 0); // B
    
    ...
    
    part_name = new_part_info.getPartName();    // 1_5_5_0
    
    ...
    
    auto new_data_part = data.createPart(
        part_name,
        data.choosePartType(expected_size, block.rows()),
        new_part_info,
        createVolumeFromReservation(reservation, volume),
        TMP_PREFIX + part_name);        // C 
    
    ...

    // D
    if (new_data_part->isStoredOnDisk())
    {
        /// The name could be non-unique in case of stale files from previous runs.
        String full_path = new_data_part->getFullRelativePath();

        if (new_data_part->volume->getDisk()->exists(full_path))
        {
            LOG_WARNING(log, "Removing old temporary directory {}", fullPath(new_data_part->volume->getDisk(), full_path));
            new_data_part->volume->getDisk()->removeRecursive(full_path);
        }

        const auto disk = new_data_part->volume->getDisk();
        disk->createDirectories(full_path);

        if (data.getSettings()->fsync_part_directory)
            sync_guard = disk->getDirectorySyncGuard(full_path);
    }

    ...

    // E
    MergedBlockOutputStream out(new_data_part, metadata_snapshot, columns, index_factory.getMany(metadata_snapshot->getSecondaryIndices()), compression_codec);
    bool sync_on_insert = data.getSettings()->fsync_after_insert;

    out.writePrefix();
    out.writeWithPermutation(block, perm_ptr);
    out.writeSuffixAndFinalizePart(new_data_part, sync_on_insert);

    ...

}
```
**A**
  
为了确保将 part 写入到磁盘成功，需要为 part 生成一个临时的名称，除了临时前缀外
```c++
static const String TMP_PREFIX = "tmp_insert_";
Int64 temp_index = data.insert_increment.get(); // A
```
还需要一个临时的 index，每个 StorageMergeTree 内有两个计数器，`insert_increment` 用于分配这个临时的index


**B**
```c++
MergeTreePartInfo new_part_info(partition.getID(metadata_snapshot->getPartitionKey().sample_block), temp_index, temp_index, 0);
...
part_name = new_part_info.getPartName();    // 1_5_5_0
```
后续到真正把part写入磁盘之前都是在内存中初始化 new_data_part，比如各种`*MergeTree`的自定义合并策略是在这一阶段完成的：
```c++
if (optimize_on_insert)
    block = mergeBlock(block, sort_description, partition_key_columns, perm_ptr);
```

**C**

这些步骤完成后，在内存中创建该 part 对象：
```c++
auto new_data_part = data.createPart(
    part_name,
    data.choosePartType(expected_size, block.rows()),
    new_part_info,
    createVolumeFromReservation(reservation, volume),
    TMP_PREFIX + part_name);
```
创建 part 时 choosePartType 函数决定了该 part 的类型，关于类型的介绍见 Clickhouse 官网的 [Data Storage](https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/mergetree/#mergetree-data-storage)。


**D**
开始进行磁盘操作，主要是创建相关的目录，并不涉及到写入数据
```c++
if (new_data_part->isStoredOnDisk())
{
    /// The name could be non-unique in case of stale files from previous runs.
    String full_path = new_data_part->getFullRelativePath();

    if (new_data_part->volume->getDisk()->exists(full_path))
    {
        LOG_WARNING(log, "Removing old temporary directory {}", fullPath(new_data_part->volume->getDisk(), full_path));
        new_data_part->volume->getDisk()->removeRecursive(full_path);
    }

    const auto disk = new_data_part->volume->getDisk();
    disk->createDirectories(full_path);

    if (data.getSettings()->fsync_part_directory)
        sync_guard = disk->getDirectorySyncGuard(full_path);
}
```
这里的 full_path 是`store/e48/e482171d-25db-4c80-87dc-ba3b25298d38/tmp_insert_1_1_1_0/`，检查一下对应的磁盘目录
```bash
➜  e482171d-25db-4c80-87dc-ba3b25298d38 ls -ls
total 8
0 drwxr-x---  2 hzq  wheel  64 Sep 17 10:14 detached
8 -rw-r-----  1 hzq  wheel   1 Sep 17 10:14 format_version.txt
0 drwxr-x---  2 hzq  wheel  64 Sep 17 10:24 tmp_insert_1_1_1_0

➜  e482171d-25db-4c80-87dc-ba3b25298d38 cd tmp_insert_1_1_1_0
➜  tmp_insert_1_1_1_0 ls -lh
```

说明到这里只是创建了目录，还未写入内容。真正对 part 文件夹下内容的写入是由类 MergedBlockOutputStream 完成的。

**E**

```c++
MergedBlockOutputStream out(new_data_part, metadata_snapshot, columns, index_factory.getMany(metadata_snapshot->getSecondaryIndices()), compression_codec);

out.writePrefix();
out.writeWithPermutation(block, perm_ptr);
out.writeSuffixAndFinalizePart(new_data_part, sync_on_insert);
```
其写入也是分为两步，第一步通过 `MergeTreeDataPartWriter::finish`完成 bin 文件、mrk文件以及主键的索引文件写入
```bash
➜  tmp_insert_1_1_1_0 ls -lh
total 24
-rw-r-----  1 hzq  wheel   118B Sep 17 10:36 data.bin
-rw-r-----  1 hzq  wheel   112B Sep 17 10:36 data.mrk3
-rw-r-----  1 hzq  wheel    16B Sep 17 10:36 primary.idx
```
然后通过`finalizePartOnDisk(new_part, part_columns, checksums, sync)`完成其余元信息的写入。
```bash
➜  tmp_insert_1_1_1_0 ls -lh
total 72
-rw-r-----  1 hzq  wheel   253B Sep 17 10:37 checksums.txt
-rw-r-----  1 hzq  wheel    79B Sep 17 10:37 columns.txt
-rw-r-----  1 hzq  wheel     1B Sep 17 10:37 count.txt
-rw-r-----  1 hzq  wheel   118B Sep 17 10:36 data.bin
-rw-r-----  1 hzq  wheel   112B Sep 17 10:36 data.mrk3
-rw-r-----  1 hzq  wheel    10B Sep 17 10:37 default_compression_codec.txt
-rw-r-----  1 hzq  wheel    16B Sep 17 10:37 minmax_devider.idx
-rw-r-----  1 hzq  wheel     8B Sep 17 10:37 partition.dat
-rw-r-----  1 hzq  wheel    16B Sep 17 10:36 primary.idx
```

#### MergeTreeData::renameTempPartAndReplace
```c++
bool MergeTreeData::renameTempPartAndReplace(
    MutableDataPartPtr & part, SimpleIncrement * increment, Transaction * out_transaction,
    std::unique_lock<std::mutex> & lock, DataPartsVector * out_covered_parts, MergeTreeDeduplicationLog * deduplication_log)
{
    ...
    if (increment)  // A
    {
        part_info.min_block = part_info.max_block = increment->get();
        part_info.mutation = 0; /// it's equal to min_block by default
        part_name = part->getNewName(part_info);
    }
    else /// Parts from ReplicatedMergeTree already have names
        part_name = part->name;
    
    LOG_TRACE(log, "Renaming temporary part {} to {}.", part->relative_path, part_name);
    
    ...
    // B
    if (auto it_duplicate = data_parts_by_info.find(part_info); it_duplicate != data_parts_by_info.end())
    {
        ...
        throw Exception(message, ErrorCodes::DUPLICATE_DATA_PART);
    }
    
    ...

    // C
    /// All checks are passed. Now we can rename the part on disk.
    /// So, we maintain invariant: if a non-temporary part in filesystem then it is in data_parts
    ///
    /// If out_transaction is null, we commit the part to the active set immediately, else add it to the transaction.
    part->name = part_name;
    part->info = part_info;
    part->is_temp = false;
    part->setState(DataPartState::PreCommitted);
    part->renameTo(part_name, true);

    auto part_it = data_parts_indexes.insert(part).first;

    ...
}
```
**A**
前面提到 StorageMergeTree 有两个计数器，这里的 increment 计数器是用于给 part 分配真正的名字的
```c++
part_info.min_block = part_info.max_block = increment->get(); 
```
**B**
从这里开始到 C 之前都是在做 part 的合法性检查

**C**
检查通过，完成两件事，将重命名后的 part 添加到 part index 中，以及将磁盘上的 temp_insert_1_1_0 重名为 new part name。在这之后就是修改一些统计信息。

#### Summary
我们重新从整体来回顾一下写入过程，对于目标是 MergeTree Engine 的一条 INSERT 语句，经过层层调用最终会执行到 `MergeTreeBlockOutputStream::write`，该方法首先将 Block 分割为 Parts，然后遍历 PartitionsWithBlock，在`MergeTreeDataWriter::writeTempPart`函数中通过构造`MergedBlockOutputStream`对象完成一个 Part 的写入。

每个新写入的 Part 名称为 `PartitionID_MinBlock_MaxBlock_Level`，尤其需要注意的是，此时 MinBlock 与 MaxBlock 一定是相等的。这里命名为 Block 个人感觉容易产生误解，因为该值实际上是 Table 内所有 Partition 共享的一个递增计数器，与每次写入的数据行数、大小无关，每次写入产生一个 part 就会使这个 ID + 1，所以这里 MinBlock 与 MaxBlcok 实际上代表的是当前 part 中的数据是由哪个“稀疏”写入范围产生的，这里加“稀疏”的意义可以通过如下例子明白：
```sql
INSERT INTO TABLE test_table VALUES(1,1,1), (2,2,2)
```
本次写入将会产生如下的 part：`1_1_1_0, 2_2_2_0`，然后我们再次写入
```sql
INSERT INTO TABLE test_table VALUES(3,3,1), (4,4,2)
```
新的 part：`1_3_3_0, 2_4_4_0`，这样的经过一次合并（准确说是两次，因为一次合并只会选择一个partition进行合并），我们会得到这样两个 part：`1_1_3_1, 2_2_4_1`。

所以合并得到新 part 的 MinBlock 与 MaxBlock 并不表示该 part 由 MinBlock 到 MaxBlock 之间的所有 part 合并得到！而是表示一个稀疏范围！这一点在不涉及到 ReplicatedMergeTree 时，不会有什么大的影响，因为不会影响到合并：`1_1_1_0`照样可以与`1_3_3_0`合并，但是在 ReplicatedMergeTree 下，缺少的 `1_2_2_0` 就很麻烦了，因为你不知道缺少的 part 是真的没有还是被写到了另一个 replicate 上，具体处理逻辑我们在介绍到 ReplicatedMergeTree 时做分析。

## Lock
### Lock Management
基类 IStorage 包含两个读写锁
```c++
IStorage {
    ...
private:
    /// Lock required for alter queries (lockForAlter). Always taken for write
    /// (actually can be replaced with std::mutex, but for consistency we use
    /// RWLock). Allows to execute only one simultaneous alter query. Also it
    /// should be taken by DROP-like queries, to be sure, that all alters are
    /// finished.
    mutable RWLock alter_lock = RWLockImpl::create();

    /// Lock required for drop queries. Every thread that want to ensure, that
    /// table is not dropped have to table this lock for read (lockForShare).
    /// DROP-like queries take this lock for write (lockExclusively), to be sure
    /// that all table threads finished.
    mutable RWLock drop_lock = RWLockImpl::create();
}
```
同时提供了几个对外接口：
```c++
/// Lock table for share. This lock must be acuqired if you want to be sure,
/// that table will be not dropped while you holding this lock. It's used in
/// variety of cases starting from SELECT queries to background merges in
/// MergeTree.
TableLockHolder lockForShare(const String & query_id, const std::chrono::milliseconds & acquire_timeout);

/// Lock table for alter. This lock must be acuqired in ALTER queries to be
/// sure, that we execute only one simultaneous alter. Doesn't affect share lock.
TableLockHolder lockForAlter(const String & query_id, const std::chrono::milliseconds & acquire_timeout);

/// Lock table exclusively. This lock must be acquired if you want to be
/// sure, that no other thread (SELECT, merge, ALTER, etc.) doing something
/// with table. For example it allows to wait all threads before DROP or
/// truncate query.
///
/// NOTE: You have to be 100% sure that you need this lock. It's extremely
/// heavyweight and makes table irresponsive.
TableExclusiveLockHolder lockExclusively(const String & query_id, const std::chrono::milliseconds & acquire_timeout);
```
INSERT：在创建 BlockIO 之前对目标 table 加 share 锁，防止写入期间 table 被 drop

```c++
BlockIO InterpreterInsertQuery::execute() {
    ...
    StoragePtr table = getTable(query);
    auto table_lock = table->lockForShare(getContext()->getInitialQueryId(), settings.lock_acquire_timeout);
    auto metadata_snapshot = table->getInMemoryMetadataPtr();
    ...
}
```
ALTER：所有的 ALTER 操作在获取 metadata 之前都加了 alter 锁，保证任意时刻只有一个 ALTER 操作在执行。
```c++
BlockIO InterpreterAlterQuery::execute() {
    ...
    StoragePtr table = DatabaseCatalog::instance().getTable(table_id, getContext());
    auto alter_lock = table->lockForAlter(getContext()->getCurrentQueryId(), getContext()->getSettingsRef().lock_acquire_timeout);
    auto metadata_snapshot = table->getInMemoryMetadataPtr();
    ...
}
```

## Metadata
Metadata 采用多版本控制，前面 INSERT 期间我们只对 table 获取了 drop 锁，那期间如果有 alter 操作修改元数据怎么办？答案是 ALTER 不会修改 INSERT 获得的 metadata，而是生成新版本的 metadata。
```c++
class IStorage {
    ...
private:
    MultiVersionStorageMetadataPtr metadata;
}
```

## MergeMutate
### selectPartsToMerge
```plantuml
@startuml
class CurrentlyMergingPartsTagger {
    - future_part : FutureMergedMutatedPart
    - reserved_space : IReservation
    - storage : StorageMergeTree &
    - tagger : CurrentlySubmergingEmergingTagger
}

CurrentlyMergingPartsTagger *-- CurrentlySubmergingEmergingTagger

class CurrentlySubmergingEmergingTagger {
    - storage : MergeTreeData &
    - emerging_part_name : String
    - submerging_parts : DataPartsVector
}


@enduml
```

