[TOC]
## 整体流程

以 INSERT INTO TABLE 为例先看一下 ReplicatedMergeTree 任务管理的整体流程
### Initial 节点
initial 节点的写入过程总体来看需要完成两个任务，首先是 part 在本地的写入，其次是在 zk 中创建一条 log 告诉其他 replica (实际上包含自己) 需要进行 fetch。
```c++
void ReplicatedMergeTreeSink::consume(Chunk chunk)
{
    ...
    auto part_blocks = storage.writer.splitBlockIntoParts(block, max_parts_per_block, metadata_snapshot);
    ...
    for (auto & current_block : part_blocks)
    {
        ...
        /// Write part to the filesystem under temporary name. Calculate a checksum.
        MergeTreeData::MutableDataPartPtr part = storage.writer.writeTempPart(current_block, metadata_snapshot, optimize_on_insert);
        String block_id = part->getZeroLevelPartBlockID();
        ...
        try
        {
            commitPart(zookeeper, part, block_id);
        }
        catch (...)
        {
            ...
            throw;
        }
    }
}
```
上面这段代码记录了 write 函数的主要流程。在 commitPart 之前的部分很简单，这里不再做详细解释，参考 MergeTree 的写入过程。
需要关注的是这里的 block_id，在 writeTempPart 中将会根据 block 中数据的内容为其计算一个 hash 值，由 {partition_id}_{hash} 组成该 block 的 block_id，后续用于 part 的 deduplication。

commitPart 函数比较复杂的部分在于各种异常处理，我们这里只列出正常处理过程的代码。
```c++
void ReplicatedMergeTreeBlockOutputStream::commitPart(
    zkutil::ZooKeeperPtr & zookeeper, MergeTreeData::MutableDataPartPtr & part, const String & block_id)
{
    ...
    String block_id_path = storage.zookeeper_path + "/blocks/" + block_id;
    auto block_number_lock = storage.allocateBlockNumber(part->info.partition_id, zookeeper, block_id_path);
    ...
    
    block_number = block_number_lock->getNumber();

    StorageReplicatedMergeTree::LogEntry log_entry;
    log_entry.type = StorageReplicatedMergeTree::LogEntry::GET_PART;
    log_entry.create_time = time(nullptr);
    log_entry.source_replica = storage.replica_name;
    log_entry.new_part_name = part->name;
    log_entry.block_id = block_id;
    ops.emplace_back(zkutil::makeCreateRequest(
        storage.zookeeper_path + "/log/log-",
        log_entry.toString(),
        zkutil::CreateMode::PersistentSequential));

    /// Information about the part.
    storage.getCommitPartOps(ops, part, block_id_path);
    MergeTreeData::Transaction transaction(storage); /// If you can not add a part to ZK, we'll remove it back from the working set.
    bool renamed = false;
    renamed = storage.renameTempPartAndAdd(part, nullptr, &transaction);
    Coordination::Responses responses;
    Coordination::Error multi_code = zookeeper->tryMultiNoThrow(ops, responses); /// 1 RTT

    transaction.commit();
    storage.merge_selecting_task->schedule();
}
```
commitPart 过程分为三步：
1. allocate block number & deduplicate
2. create GET_PART log, record part in zookeeper
3. rename temp part

结合一个实际的例子来看看以上三个步骤完成的具体操作。

* **allocate block number & deduplicate**

```bash
INSERT INTO TABLE insertDebug VALUES (100, 10000, 1),(101, 10001, 2),(102, 10002, 3),(103, 10003, 4),(104, 10004, 1)
```
block 切分之后得到的第一个 part 内容包含 `(100, 10000, 1),(104, 10004, 1)`，block_id 内容根据 part 内容计算这里为`1_11848747669222048964_7469084187050794676`，用于数据输入时候的去重。

```c++
std::optional<EphemeralLockInZooKeeper>
StorageReplicatedMergeTree::allocateBlockNumber(
    const String & partition_id, const zkutil::ZooKeeperPtr & zookeeper, const String & zookeeper_block_id_path, const String & zookeeper_path_prefix)
{
    ...
    /// Lets check for duplicates in advance, to avoid superfluous block numbers allocation
    Coordination::Requests deduplication_check_ops;
    if (!zookeeper_block_id_path.empty())
    {
        deduplication_check_ops.emplace_back(zkutil::makeCreateRequest(zookeeper_block_id_path, "", zkutil::CreateMode::Persistent));
        deduplication_check_ops.emplace_back(zkutil::makeRemoveRequest(zookeeper_block_id_path, -1));
    }

    String block_numbers_path = fs::path(zookeeper_table_path) / "block_numbers";
    String partition_path = fs::path(block_numbers_path) / partition_id;
    ...
    try
    {
        lock = EphemeralLockInZooKeeper(
            fs::path(partition_path) / "block-", fs::path(zookeeper_table_path) / "temp", *zookeeper, &deduplication_check_ops);
    }
    catch (const zkutil::KeeperMultiException & e)
    {
        if (e.code == Coordination::Error::ZNODEEXISTS && e.getPathForFirstFailedOp() == zookeeper_block_id_path)
            return {};

        throw Exception("Cannot allocate block number in ZooKeeper: " + e.displayText(), ErrorCodes::KEEPER_EXCEPTION);
    }
    catch (const Coordination::Exception & e)
    {
        throw Exception("Cannot allocate block number in ZooKeeper: " + e.displayText(), ErrorCodes::KEEPER_EXCEPTION);
    }

    return {std::move(lock)};

}
```
首先创建用于检查是否有重复内容 part 的操作，检查的原理就是尝试在 table_path/blocks 下创建一个与 block_id 同名的持久化的 znode，如果创建成功说明未重复，否则说明该 part 为重复 part。注意，这里如果创建成功，还会紧跟一个 remove node 操作，后续在 record part in zookeeper 的时候会将该 node 重新创建。在 EphemeralLockInZooKeeper 中将该操作提交 zookeeper 执行，并且尝试 allocate block number

考虑多写情景，如果客户端在两个 replica 上同时写某个 partition，我们需要保证 block number 在两个 replica 上的顺序性。该顺序性是通过 zk 的 [sequential node](https://zookeeper.apache.org/doc/r3.4.10/zookeeperProgrammers.html#Sequence+Nodes+--+Unique+Naming) 实现的。zk 中创建 znode 共有[四种模式](https://zookeeper.apache.org/doc/r3.2.2/api/org/apache/zookeeper/CreateMode.html)，我们这里需要关注的是`EPHEMERAL_SEQUENTIAL`：The znode will be deleted upon the client's disconnect, and its name will be appended with a monotonically increasing number.

EphemeralLockInZooKeeper 对象构造时会尝试在 zk 上创建两个节点，并且完成提供的去重操作。两个节点的类型均为 `EPHEMERAL_SEQUENTIAL`，一个是代表正在被写入的part，路径为 table_path/block_numbers/partitiond_id/block_xxxxx ，另一个是 table_path/temp/abandonable_lock-xxxxx，前者引用后者。

以我们写入的第一个 part 为例，partition_id = 1，由于是第一次在当前 partition 插入 znode，那么这个 block 就可以获得 number 0000000000，同样 temp 下也是第一次插入 znode，那么其唯一的 id 也是 0000000000

<center>
<img alt="picture 1" src="../../images/fd7d7846e65030a93516b15c70dec358468f4af0a1467a09ab521d7a266bdedc.png" height="400px" />  
</center>

当我们处理完第一个 part，连接断开，partition 下的 `block_` 和 temp 下的 `abandonable_lock` 都会被自动删除，第二个 part 的 partition id 为 2，重复上述过程，我们可以得到

<center>
<img alt="picture 2" src="../../images/19579eca222a612ebd53bccf43a501762105ee34095efaf67a30f276e5616c2d.png" height="400px"/>  
</center>
 
上述过程是在 EphemeralLockInZooKeeper 对象构造时完成的，返回的 lock 对象将会包含 `block_` 后跟随的 sequential number，然后该 number 将会被赋值给 part
```c++
lock = EphemeralLockInZooKeeper(
            partition_path + "/block-", zookeeper_path + "/temp", *zookeeper, &deduplication_check_ops);

...
block_number = block_number_lock->getNumber();
part->info.min_block = block_number;
part->info.max_block = block_number;
...
```
实际上只需要 block_ 节点就足够保证 block number 的顺序性了，不是很明白这里 abandonable_lock_ 的作用。（代码注释是为了后向兼容）

* **create GET_PART log, record part in zookeeper**

当成功获得 block_number_lock 之后，在 zk 中创建一条 GET_PART log，内容如下：
```bash
[zk: localhost:2181(CONNECTED) 36] get /clickhouse/tables/01/insertDebug/log/log-0000000000
format version: 4
create_time: 2021-10-02 12:52:03
source replica: r1
block_id: 1_11848747669222048964_7469084187050794676
get
1_1_1_0
part_type: Compact
```
然后下一步将之前 insert 的临时 part `tmp_insert_1_1_1_0` 重命名为 `1_1_1_0`，如果本次操作成功，将会把 part 信息真正注册到 zk 中如下：
```bash
[zk: localhost:2181(CONNECTED) 37] ls /clickhouse/tables/01/insertDebug/blocks
[1_11848747669222048964_7469084187050794676]
[zk: localhost:2181(CONNECTED) 39] get /clickhouse/tables/01/insertDebug/blocks/1_11848747669222048964_7469084187050794676
1_1_1_0
[zk: localhost:2181(CONNECTED) 42] ls /clickhouse/tables/01/insertDebug/block_numbers
[1]
```
### Follower 节点
目前我们完成了在 initail 节点的 part 写入，现在需要完成将 initial 节点写入的 part 同步到 follower 节点的工作。

#### 线程模型

首先明确几个概念：
- task：代表传递给 thread pool 的一个任务。创建 task 可以理解为是交给线程池一个去执行的任务，但是绝对不等价于创建一个执行线程。task 将 thread pool 的接口封装后对外抽象出自己的接口，比如`schedule()`接口可以将本 task 直接前置到 thread pool 的队列头，如果有空闲线程本 task 将会被立刻执行。
- thread：本质就是在对象构造时创建一个 task。区别在于 thread 对象没有对外提供主动调度自己执行时机的接口。也就是说，所有交给 thread 执行的函数何时能够执行都是随缘的。
- executor：将 task 与一个逻辑 thread pool 结合在一起抽象出的对使用者来说功能更加丰富的对象。逻辑 thread pool 是指并不是真的创建新的线程，更加丰富的功能是指提供了可以控制有多少线程去执行 task。

这几个概念比较容易理解，如果不理解也没关系，有个大致概念，后面结合例子会看懂的。我们先来整体看看 ReplicatedMergeTree 的构造函数：
```c++
StorageReplicatedMergeTree::StorageReplicatedMergeTree(ContextPtr context_, ...) : MergeTreeData(context_, ...)
    ...
    , background_executor(*this, getContext())
    , background_moves_executor(*this, getContext())
    , cleanup_thread(*this)
    , part_check_thread(*this)
    , restarting_thread(*this)
    , replicated_fetches_pool_size(getContext()->getSettingsRef().background_fetches_pool_size)
    ...
{
    queue_updating_task = getContext()->getSchedulePool().createTask(
        getStorageID().getFullTableName() + " (StorageReplicatedMergeTree::queueUpdatingTask)", [this]{ queueUpdatingTask(); });

    mutations_updating_task = getContext()->getSchedulePool().createTask(
        getStorageID().getFullTableName() + " (StorageReplicatedMergeTree::mutationsUpdatingTask)", [this]{ mutationsUpdatingTask(); });

    merge_selecting_task = getContext()->getSchedulePool().createTask(
        getStorageID().getFullTableName() + " (StorageReplicatedMergeTree::mergeSelectingTask)", [this] { mergeSelectingTask(); });

    /// Will be activated if we win leader election.
    merge_selecting_task->deactivate();

    mutations_finalizing_task = getContext()->getSchedulePool().createTask(
        getStorageID().getFullTableName() + " (StorageReplicatedMergeTree::mutationsFinalizingTask)", [this] { mutationsFinalizingTask(); });
    
    ...
}
```
构造函数内部，其中 cleanup_thread、part_check_thread、restarting_thread、queue_updating_task、mutations_updating_task、merge_selecting_task、mutations_finalizing_task 都是往**全局的被所有表共用的** Background Schedule Pool 中塞进一个 task，该线程池大小由参数`background_schedule_pool_size`控制，最新的clickhouse master里默认值为 128 [PR#25072](https://github.com/ClickHouse/ClickHouse/pull/25072)

初始化列表里有两个 executor，其中比较关键的是 `BackgroundJobsExecutor`。`BackgroundJobsExecutor`对象构造时创建了两个**逻辑**线程池。一个线程池负责执行 MERGE_MUTATE 任务，另一个负责执行 FETCH 任务。前者大小由参数`background_pool_size`决定，后者由参数`background_fetches_pool_size`决定。

初始化列表里还创建了三个 thread，它们没有提供主动调度自己执行的接口，通常执行相对不太“重要”的任务。

#### part 同步

**ReplicatedMergeTreeQueue::pullLogsToQueue**

前面我们提到，initial 节点会在 zk 中创建 log，告诉 follower 节点需要进行 part fetch。follower 节点的 queue_updating_task 的任务是从 zk 拉取一个批次的 log 到本地，并且在zk的 table/replica/{replica}/queue 中添加一条 queue-xxxx ，表示当前 log 正在/已经被执行，最后触发 background_executor。

**DataProcessing**
一切顺利的话，前面一步 queue 中添加的 log entry 就该被 getDataProcessingJob 消费掉，该函数由 
```c++
std::optional<JobAndPool> StorageReplicatedMergeTree::getDataProcessingJob()
{
    /// This object will mark the element of the queue as running.
    ReplicatedMergeTreeQueue::SelectedEntryPtr selected_entry = selectQueueEntry();
    ...
    processQueueEntry(selected_entry);
    ...
}
```
selectQueueEntry 函数决定了某个 log 是否应该被执行，其详细逻辑在后面单独介绍。**一旦某个 log 被选中可以执行，则其在 system.replication_queue 中对应项的 num_tries 会加一**

**executeLogEntry**

对于写入过程产生的 GET_PART log，如果 part_name 在当前 replica 存在（包括 Committed/PreCommitted 状态）且在 zk 的 replica_path/parts/part_name 下存在，则不会进行 fetch。否则我们将会执行 fetch，这里还有其他的一些判断，留在后面和MERGE_PART一起介绍。

**executeFetch**
```c++
bool StorageReplicatedMergeTree::executeFetch(LogEntry & entry)
{
    String replica = findReplicaHavingCoveringPart(entry, true);
    ...
    String part_name = entry.actual_new_part_name.empty() ? entry.new_part_name : entry.actual_new_part_name;
    fetchPart(part_name, metadata_snapshot, zookeeper_path + "/replicas/" + replica, false, entry.quorum));
    ...
    return true;
}
```
fetchPart 的具体执行过程就不写了。当该函数返回 true 时，ReplicatedMergeTreeQueue 会将本次 log 从 replica/{replica}/queue 下删除


## 关键步骤 
### ReplicatedMergeTreeQueue::pullLogsToQueue

通过前面几个典型任务的流程分析，我们对 ReplicationMergeTree 的任务处理有了整体印象，大致分为三个阶段：
1. log 创建：由 initial 节点在 zk 的 log 下创建一条 log-xxxxx 
2. 任务队列更新：folower 节点监听 log，将新的 log 拉取到本地，更新 zk 中 replica/{replica}/queue 的状态，触发 background_executor
3. background_executor 消费 queue

ReplicatedMergeTreeQueue 在整个过程中充当关键的角色，该类的实现决定了如何拉取 log，当前 log 是否应该被执行，以及 replica/{replica}/queue 下节点如何更新。

其关键的数据成员如下：
```plantuml
class ReplicatedMergeTreeQueue {
    - zookeeper_path : String
    - replica_path : String
    - state_mutex : mutex
    - current_parts : ActiveDataPartSet
    - queue : Queue
    - future_parts : std::map<String, LogEntryPtr>
    - virtual_parts : ActiveDataPartSet
    - pull_logs_to_queue_mutex : mutex
    - alter_sequence : ReplicatedMergeTreeAltersSequence
    + selectEntryToProcess(merger_mutator, MergeTreeData) : SelectedEntryPtr
    + processEntry(zookeeper, LogEntryPtr, func) : bool
}
```
**pullLogsToQueue** 

```c++
int32_t ReplicatedMergeTreeQueue::pullLogsToQueue(zkutil::ZooKeeperPtr zookeeper, Coordination::WatchCallback watch_callback)
{
    ...
    String index_str = zookeeper->get(replica_path + "/log_pointer");
    Strings log_entries = zookeeper->getChildrenWatch(zookeeper_path + "/log", nullptr, watch_callback);
    ...
    log_entries.erase(所有小于index的log);
    ...
    
    std::sort(log_entries.begin(), log_entries.end());
    for (size_t entry_idx = 0, num_entries = log_entries.size(); entry_idx < num_entries;) {
        /// 一次取 current_multi_batch_size 条 log 去处理
        auto begin = log_entries.begin() + entry_idx;
        auto end = entry_idx + current_multi_batch_size >= log_entries.size()
                ? log_entries.end()
                : (begin + current_multi_batch_size);
        auto last = end - 1;

        zkutil::AsyncResponses<Coordination::GetResponse> futures;
        futures.reserve(end - begin);

        for (auto it = begin; it != end; ++it)
            futures.emplace_back(*it, zookeeper->asyncGet(zookeeper_path + "/log/" + *it));

        for (auto & future : futures)
        {
            ...
            /// 在本 replica 的 queue 下创建一条 queue_xxx 纪录 log 的执行状态
            ops.emplace_back(zkutil::makeCreateRequest(
                    replica_path + "/queue/queue-", res.data, zkutil::CreateMode::PersistentSequential));
            ...
        }
        /// 更新 log_pointer 指向下一条未处理的 log
        ops.emplace_back(zkutil::makeSetRequest(
                replica_path + "/log_pointer", toString(last_entry_index + 1), -1));

        /// Now we have successfully updated the queue in ZooKeeper. Update it in RAM.

        try
        {
            ...
        }

        storage.background_executor.triggerTask();
    }
    return stat.version;
}
```

pullLogsToQueue 函数主要由 background_schedule_pool 中的线程执行，其执行的次数反应在监控指标里对应 ClickHouseMetrics_BackgroundSchedulePoolTask

任何时刻只有一个线程能够执行 ReplicatedMergeTreeQueue::pullLogsToQueue
```c++
std::lock_guard lock(pull_logs_to_queue_mutex);
```
获取 `replica/{replica}/log_pointer`保存的值，并且通过 zookeeper list 请求，获取 `log` 下的所有节点名称，名称格式为`log-xxxxxxxx`，updateMutations 函数用于控制 mutation 操作顺序，到涉及到 mutation 操作时再介绍。
```c++
String index_str = zookeeper->get(replica_path + "/log_pointer");
UInt64 index;

/// The version of "/log" is modified when new entries to merge/mutate/drop appear.
Coordination::Stat stat;
zookeeper->get(zookeeper_path + "/log", &stat);

Strings log_entries = zookeeper->getChildrenWatch(zookeeper_path + "/log", nullptr, watch_callback);

updateMutations(zookeeper);
```
下一步在内存中删除所有index小于当前replica的log pointer的所有log，之前的log_entries包含log下所有的节点名称，getChildren 最终调用的是 zk 的 list 方法，当 log 下的子节点数量非常多的时候，list一次可能会花费相当多的时间（待测）：
```c++
log_entries.erase(所有小于index的log);
```
下一步，将 current_multi_batch_size 条 log 加进内存中的 queue 对象，下次循环将会拉 current_multi_batch_size * 2 条 log，直到 current_multi_batch_size 达到 100
```c++
for (size_t entry_idx = 0, num_entries = log_entries.size(); entry_idx < num_entries;)
{
    auto begin = log_entries.begin() + entry_idx;
    auto end = entry_idx + current_multi_batch_size >= log_entries.size()
        ? log_entries.end()
        : (begin + current_multi_batch_size);
    auto last = end - 1;
    /// Increment entry_idx before batch size increase (we copied at most current_multi_batch_size entries)
    entry_idx += current_multi_batch_size;

    if (current_multi_batch_size < MAX_MULTI_OPS)
                current_multi_batch_size = std::min<size_t>(MAX_MULTI_OPS, current_multi_batch_size * 2);
    ...
}
```
前一步 getChildrenWatch 获取的 log_entries 里保存的只是 node 的名字，没有获取 node 中的内容，在循环内，下一步就是通过 asyncGet 方法获取 node 的内容
```c++
LOG_DEBUG(log, "Pulling {} entries to queue: {} - {}", (end - begin), *begin, *last);

zkutil::AsyncResponses<Coordination::GetResponse> futures;
```
`zkutil::AsyncResponses<Coordination::GetResponse> futures`是一个vector，保存的每个元素为 string 类型的 log-xxxxx，和一个 Zookeeper::futureGet 对象，
```c++
Coordination::Requests ops;
std::vector<LogEntryPtr> copied_entries;
copied_entries.reserve(end - begin);

for (auto & future : futures)
{
    Coordination::GetResponse res = future.second.get();

    copied_entries.emplace_back(LogEntry::parse(res.data, res.stat));

    ops.emplace_back(zkutil::makeCreateRequest(
        replica_path + "/queue/queue-", res.data, zkutil::CreateMode::PersistentSequential));

    const auto & entry = *copied_entries.back();
    if (entry.type == LogEntry::GET_PART)
    {
        std::lock_guard state_lock(state_mutex);
        if (entry.create_time && (!min_unprocessed_insert_time || entry.create_time < min_unprocessed_insert_time))
        {
            min_unprocessed_insert_time = entry.create_time;
            min_unprocessed_insert_time_changed = min_unprocessed_insert_time;
        }
    }
}
```
上述这段循环结束后，`copied_entries`就会包含 log 节点的名称及其内容，同时在 replica/{replica}/queue 下创建 queue-xxxxx，表示本 replica 正在执行该 log
```c++
ops.emplace_back(zkutil::makeSetRequest(
    replica_path + "/log_pointer", toString(last_entry_index + 1), -1));

if (min_unprocessed_insert_time_changed)
    ops.emplace_back(zkutil::makeSetRequest(
        replica_path + "/min_unprocessed_insert_time", toString(*min_unprocessed_insert_time_changed), -1));

auto responses = zookeeper->multi(ops);
```
到这里，zookeeper 中的状态我们已经更新完成。后续是更新内存状态
```c++
try
{
    std::lock_guard state_lock(state_mutex);

    for (size_t copied_entry_idx = 0, num_copied_entries = copied_entries.size(); copied_entry_idx < num_copied_entries; ++copied_entry_idx)
    {
        String path_created = dynamic_cast<const Coordination::CreateResponse &>(*responses[copied_entry_idx]).path_created;
        copied_entries[copied_entry_idx]->znode_name = path_created.substr(path_created.find_last_of('/') + 1);

        std::optional<time_t> unused = false;
        insertUnlocked(copied_entries[copied_entry_idx], unused, state_lock);
    }

    last_queue_update = time(nullptr);
}
```
更新内存状态的核心目标就是将 copied_entries 中的元素添加到类型为`std::list<LogEntryPtr>`的 queue 对象中，由函数 insertInlocked 完成。

内存状态更新完成后，尝试让后台执行线程池消费log
```c++
storage.background_executor.triggerTask();
```

pullLogsToQueue 函数在执行过程中会打印两条重要日志，第一条是在**每次**循环开始，更新 zk 中的 queue 以及 log pointer 之前打印的：
```c++
LOG_DEBUG(log, "Pulling {} entries to queue: {} - {}", (end - begin), *begin, *last);
```
第二条是在**每次循环结束**，更新完内存中的 queue 的状态后打印的：
```c++
LOG_DEBUG(log, "Pulled {} entries to queue.", copied_entries.size());
```
这两条日志的时间间隔，表示每次在 zk 的 replica/{replica}/queue 中创建节点并且更新本地内存 queue 所花费的时间。

线上真实的日志记录：
```txt
2021.10.28 15:29:59.682800 [ 14506 ] {} <Debug> xxx (ReplicatedMergeTreeQueue): Pulling 6 entries to queue: log-0000989928 - log-0000989933

2021.10.28 15:29:59.873588 [ 14506 ] {} <Debug> xxx (ReplicatedMergeTreeQueue): Pulled 6 entries to queue.
```
这里 6 条 log，更新 zk 以及内存需要 200 ms。
在另一个一直很健康的集群里，日志如下：
```txt
2021.11.19 10:45:27.829720 [ 72036 ] {} <Debug> xxx (ReplicatedMergeTreeQueue): Pulling 1 entries to queue: log-0008538308 - log-0008538308

2021.11.19 10:45:27.833962 [ 72036 ] {} <Debug> xxx (ReplicatedMergeTreeQueue): Pulled 1 entries to queue.
```
区别在于正常集群通常一次只会 pull 一条 log，并且更新 zk 速度很快。


### ReplicatedMergeTreeQueue::selectEntryToProcess

该函数通常在 StorageReplicatedMergeTree::getDataProcessingJob 中执行，与 ReplicatedMergeTreeQueue::processEntry 成对配合完成一条 log 的执行。该函数的逻辑很简洁：
```c++
ReplicatedMergeTreeQueue::SelectedEntryPtr ReplicatedMergeTreeQueue::selectEntryToProcess(MergeTreeDataMergerMutator & merger_mutator, MergeTreeData & data)
{
    LogEntryPtr entry;

    std::lock_guard lock(state_mutex);

    for (auto it = queue.begin(); it != queue.end(); ++it)
    {
        if ((*it)->currently_executing)
            continue;

        if (shouldExecuteLogEntry(**it, (*it)->postpone_reason, merger_mutator, data, lock))
        {
            entry = *it;
            /// We gave a chance for the entry, move it to the tail of the queue, after that
            /// we move it to the end of the queue.
            queue.splice(queue.end(), queue, it);
            break;
        }
        else
        {
            ++(*it)->num_postponed;
            (*it)->last_postpone_time = time(nullptr);
        }
    }

    if (entry)
        return std::make_shared<SelectedEntry>(entry, std::unique_ptr<CurrentlyExecuting>{ new CurrentlyExecuting(entry, *this) });
    else
        return {};
}
```
总结其中的关键点：
1. selectEntryToProcess 从 queue 中一次选择一条可执行的 log，一旦某个 log 被选择执行，它就会被 move 到队尾
2. 若某个 log 被 shouldExecuteLogEntry 判断不能执行，它将被保留在 queue 中原始位置，并且将其 num_postponed 加一，该值可以通过 system.replication_queue 看到。
3. 对于被选择可以执行的 log，为其创建一个 SelectedEntry 对象，在该对象存在期间，log 会被标记为正在执行，其 num_tries 字段被加一

### ReplicatedMergeTreeQueue::shouldExecuteLogEntry
该函数决定一条 queue 中的 log，是否应该被交给 executeLogEntry 函数去处理。shouldExecuteLogEntry 会针对不同类型的 log 做相应的判断，我们这里重点关注两类 log，一个是 GET_PART，另一类是 MERGE_PARTS。
```c++
bool ReplicatedMergeTreeQueue::shouldExecuteLogEntry(
    const LogEntry & entry,
    String & out_postpone_reason,
    MergeTreeDataMergerMutator & merger_mutator,
    MergeTreeData & data,
    std::lock_guard<std::mutex> & state_lock) const
{
    ...
    if ((entry.type == LogEntry::GET_PART || entry.type == LogEntry::ATTACH_PART)
        && !storage.canExecuteFetch(entry, out_postpone_reason))
    {
        /// Don't print log message about this, because we can have a lot of fetches,
        /// for example during replica recovery.
        return false;
    }
    if (entry.type == LogEntry::MERGE_PARTS || entry.type == LogEntry::MUTATE_PART)
    {
        /** If any of the required parts are now fetched or in merge process, wait for the end of this operation.
          * Otherwise, even if all the necessary parts for the merge are not present, you should try to make a merge.
          * If any parts are missing, instead of merge, there will be an attempt to download a part.
          * Such a situation is possible if the receive of a part has failed, and it was moved to the end of the queue.
          */
        size_t sum_parts_size_in_bytes = 0;
        for (const auto & name : entry.source_parts)
        {
            if (future_parts.count(name))
            {
                const char * format_str = "Not executing log entry {} of type {} for part {} "
                                          "because part {} is not ready yet (log entry for that part is being processed).";
                LOG_TRACE(log, format_str, entry.znode_name, entry.typeToString(), entry.new_part_name, name);
                /// Copy-paste of above because we need structured logging (instead of already formatted message).
                out_postpone_reason = fmt::format(format_str, entry.znode_name, entry.typeToString(), entry.new_part_name, name);
                return false;
            }

            ....
        }

        if (merger_mutator.merges_blocker.isCancelled())
        {
            const char * format_str = "Not executing log entry {} of type {} for part {} because merges and mutations are cancelled now.";
            ....
            return false;
        }

        if (merge_strategy_picker.shouldMergeOnSingleReplica(entry))
        {
            auto replica_to_execute_merge = merge_strategy_picker.pickReplicaToExecuteMerge(entry);

            if (replica_to_execute_merge && !merge_strategy_picker.isMergeFinishedByReplica(replica_to_execute_merge.value(), entry))
            {
                String reason = "Not executing merge for the part " + entry.new_part_name
                    +  ", waiting for " + replica_to_execute_merge.value() + " to execute merge.";
                out_postpone_reason = reason;
                return false;
            }
        }

        UInt64 max_source_parts_size = entry.type == LogEntry::MERGE_PARTS ? merger_mutator.getMaxSourcePartsSizeForMerge()
                                                                           : merger_mutator.getMaxSourcePartSizeForMutation();
        /** If there are enough free threads in background pool to do large merges (maximal size of merge is allowed),
          * then ignore value returned by getMaxSourcePartsSizeForMerge() and execute merge of any size,
          * because it may be ordered by OPTIMIZE or early with different settings.
          * Setting max_bytes_to_merge_at_max_space_in_pool still working for regular merges,
          * because the leader replica does not assign merges of greater size (except OPTIMIZE PARTITION and OPTIMIZE FINAL).
          */
        const auto data_settings = data.getSettings();
        bool ignore_max_size = false;
        if (entry.type == LogEntry::MERGE_PARTS)
        {
            ignore_max_size = max_source_parts_size == data_settings->max_bytes_to_merge_at_max_space_in_pool;

            if (isTTLMergeType(entry.merge_type))
            {
                if (merger_mutator.ttl_merges_blocker.isCancelled())
                {
                    const char * format_str = "Not executing log entry {} for part {} because merges with TTL are cancelled now.";
                    ...
                    return false;
                }
                size_t total_merges_with_ttl = data.getTotalMergesWithTTLInMergeList();
                if (total_merges_with_ttl >= data_settings->max_number_of_merges_with_ttl_in_pool)
                {
                    const char * format_str = "Not executing log entry {} for part {}"
                        " because {} merges with TTL already executing, maximum {}.";
                    ...
                    return false;
                }
            }
        }
        if (!ignore_max_size && sum_parts_size_in_bytes > max_source_parts_size)
        {
            const char * format_str = "Not executing log entry {} of type {} for part {}"
                " because source parts size ({}) is greater than the current maximum ({}).";
            ...    
            return false;
        }
        ...
    }
    
    ...
}
```
对于 GET_PART 类型的 log, 其检查逻辑在 StorageReplicatedMergeTree::canExecuteFetch 中
```c++
bool StorageReplicatedMergeTree::canExecuteFetch(const ReplicatedMergeTreeLogEntry & entry, String & disable_reason) const
{
    if (fetcher.blocker.isCancelled())
    {
        disable_reason = fmt::format("Not executing fetch of part {} because replicated fetches are cancelled now.", entry.new_part_name);
        return false;
    }

    size_t busy_threads_in_pool = CurrentMetrics::values[CurrentMetrics::BackgroundFetchesPoolTask].load(std::memory_order_relaxed);
    if (busy_threads_in_pool >= replicated_fetches_pool_size)
    {
        disable_reason = fmt::format("Not executing fetch of part {} because {} fetches already executing, max {}.", entry.new_part_name, busy_threads_in_pool, replicated_fetches_pool_size);
        return false;
    }

    if (replicated_fetches_throttler->isThrottling())
    {
        disable_reason = fmt::format("Not executing fetch of part {} because fetches have already throttled by network settings "
                                     "<max_replicated_fetches_network_bandwidth> or <max_replicated_fetches_network_bandwidth_for_server>.", entry.new_part_name);
        return false;
    }

    return true;
}
```
主要是三个可能的原因会导致 GET_PART log 不被执行：
1. 主动禁止了 Replicated Fetch
2. 后台执行 Fetch 任务的线程已经达到上限，该上限由 users.xml 的 background_fetches_pool_size 决定
3. Fetch 的网络带宽限制

最常见的 GET_PART log 被推迟是因为原因2。

对于 MERGE_PARTS log，值得注意的被推迟执行的原因为：
1. future_parts 中包含了 merge 需要的 source parts
2. 如果是 ttl merge，那么同时可以执行的 ttl merge 不能超过两个
3. merge 的 source parts size 大于 max_source_parts_size 时，当前 merge 会被推迟执行。

future_parts 是 ReplicatedMergeTreeQueue 的一个成员变量，当某条 log 被函数 selectEntryToProcess 选择，为其创建标记其正在执行的CurrentlyExecuting对象时，会将 log 的 new_part_name 字段添加到 future_parts 中，当 CurrentlyExecuting 对象被析构的时候，会从 future_parts 中将该字段删除。

## 异常处理



本小节介绍一条 log 何时会被认为不应该执行，以及偏离正常执行路径后会发生什么。

### Log 何时 should not execute

关键函数`ReplicatedMergeTreeQueue::shouldExecuteLogEntry`

**关键路径1**

如果 log.new_part_name 包含在 queue.future_parts 中，则 log 本次不会被执行。
```c++
/// If our entry produce part which is already covered by
/// some other entry which is currently executing, then we can postpone this entry.
for (const String & new_part_name : entry.getVirtualPartNames(format_version))
{
    if (!isNotCoveredByFuturePartsImpl(entry.znode_name, new_part_name, out_postpone_reason, state_lock))
        return false;
}
```
`isNotCoveredByFuturePartsImpl`函数做如下检查：如果 new_part_name 被包含在另一个正在被执行的 log 的 new_part_name 中，则当前 log 不会被执行。比如：
```sql
Not executing log entry queue-0000733298 for part 1635091200_22325_22325_0 because it is covered by part 1635091200_0_22330_3205 that is currently executing.
```
这条 GET_PART log 要 fetch 的 part name 是 1635091200_22325_22325_0，被另一条 MERGE_PART 将要生成的 1635091200_0_22330_3205 所包含，所以当前 GET_PART log 不会被执行。

当另一条 log 执行完成后，下次执行 isNotCoveredByFuturePartsImpl 将会成功。

future_parts 

**关键路径2**
```c++
/// Check that fetches pool is not overloaded
if (entry.type == LogEntry::GET_PART && !storage.canExecuteFetch(entry, out_postpone_reason))
{
    /// Don't print log message about this, because we can have a lot of fetches,
    /// for example during replica recovery.
    return false;
}
```
## 其他任务
### DROP PARTS
以如下操作为例
```sql
create table dropPartition (key Int64, value Int64, devider Int64) engine=ReplicatedMergeTree('/clickhouse/tables/01/dropPartition', '{replica}') order by key partition by devider

insert into table dropPartition values (100,100,1),(101,101,2),(99,99,3),(88,88,1)
```

```sql
SELECT
    partition,
    name AS part,
    partition_id,
    rows,
    path
FROM system.parts
WHERE table = 'dropPartition'

Query id: 57b9daff-7f93-4db4-b5b5-d78ef8acdd29

┌─partition─┬─part────┬─partition_id─┬─rows─┬─path─────────────────────────────────────────────────────────────────────────┐
│ 1         │ 1_0_0_0 │ 1            │    2 │ /tmp/clickhouse-data/store/f4e/f4e2a330-2098-434b-babf-4982c9365d53/1_0_0_0/ │
│ 2         │ 2_0_0_0 │ 2            │    1 │ /tmp/clickhouse-data/store/f4e/f4e2a330-2098-434b-babf-4982c9365d53/2_0_0_0/ │
│ 3         │ 3_0_0_0 │ 3            │    1 │ /tmp/clickhouse-data/store/f4e/f4e2a330-2098-434b-babf-4982c9365d53/3_0_0_0/ │
└───────────┴─────────┴──────────────┴──────┴──────────────────────────────────────────────────────────────────────────────┘
```

DROP PARTITION 的整体执行分为两步：
1. 在 zk 创建任务
2. 拉取 zk 中的任务进行处理

第一阶段由函数 dropPartition 完成：
```c++
// StorageReplicatedMergeTree.cpp
void StorageReplicatedMergeTree::dropPartition(...) {
    ...
    String partition_id = getPartitionIDFromQuery(partition, query_context);
    /// Step1 在 zk 中创建 log-entry
    did_drop = dropAllPartsInPartition(...);
    if (did_drop) 
    {
        /// If necessary, wait until the operation is performed on itself or on all replicas.
        ...
    }
    ...
}
```
dropAllPartsInPartition 在 zookeeper 中创建如下内容节点
```txt
[zk: localhost:2181(CONNECTED) 15] get /clickhouse/tables/01/dropPartition/log/log-0000000003
format version: 4
create_time: 2021-09-15 14:42:15
source replica: clickhouse01
block_id:
drop
3_0_1_999999999
```
创建完成后 dropPartition 函数根据 users.xml 中的 `<replication_alter_partitions_sync>` 参数决定是否等待本次 drop 被所有节点完全执行。

第二阶段函数 executeDropRange 处理前一个阶段在 zk 中创建的 log entry。删除过程也是分为两个阶段执行：
1. 修改需要被删除的part的 remove_time 为现在
2. 调度 cleanup_thread 主动删除 old parts，并且删除 zk 中 parts 信息

```c++
void StorageReplicatedMergeTree::executeDropRange(const LogEntry & entry)
{
    ...
    queue.removePartProducingOpsInRange(getZooKeeper(), drop_range_info, entry);
    ...
    /// 这一步遍历已有的part，设置需要被删除 part 的 remove_time 为现在
    parts_to_remove = removePartsInRangeFromWorkingSet(drop_range_info, true, true, data_parts_lock);

    if (entry.detach)
    {
        /// If DETACH clone parts to detached/ directory
        for (const auto & part : parts_to_remove)
        {
            part->makeCloneInDetached("", metadata_snapshot);
        }
    }

    /// Forcibly remove parts from ZooKeeper
    tryRemovePartsFromZooKeeperWithRetries(parts_to_remove);

    if (entry.detach)
        LOG_DEBUG(log, "Detached {} parts inside {}.", parts_to_remove.size(), entry.new_part_name);
    else
        LOG_DEBUG(log, "Removed {} parts inside {}.", parts_to_remove.size(), entry.new_part_name);

    /// We want to remove dropped parts from disk as soon as possible
    /// To be removed a partition should have zero refcount, therefore call the cleanup thread at exit
    parts_to_remove.clear();
    /// clean up thread 真正将数据从磁盘删除
    cleanup_thread.wakeup();
```
cleanup_thread 是后台线程，周期执行
```c++
void ReplicatedMergeTreeCleanupThread::iterate() {
    storage.clearOldPartsAndRemoveFromZK();
    ...
}
```

```c++
void StorageReplicatedMergeTree::clearOldPartsAndRemoveFromZK() {
    ...
    /// 判断某个 part 是否为 old part 的依据是其 remove_time
    DataPartsVector parts = grabOldParts();
    ...
    
    /// Remove parts from filesystem and finally from data_parts
    if (!parts_to_remove_from_filesystem.empty())
    {
        removePartsFromFilesystem(parts_to_remove_from_filesystem);
        removePartsFinally(parts_to_remove_from_filesystem);

        LOG_DEBUG(log, "Removed {} old parts", parts_to_remove_from_filesystem.size());
    }
    ...

    removePartsFromZooKeeper(zookeeper, part_names_to_delete_completely, &part_names_to_retry_deletion);
}
```
### DELETE WHERE
`ALTER TABLE ... DELETE WEHER ...`

### ATTACH PARTITION
`ALTER table attach_debug ATTACH PARTITION 10001`

调用链：

    InterpreterAlterQuery::execute
        MergeTreeData::alterPartition
            StorageMergeTree::attachPartition
                MergeTreeData::tryLoadPartsToAttach
                StorageMergeTree::renameTempPartAndAdd

`ATTACH PARTITION` 作用是将处于 `detached` 目录下的 part 重新添加到 table 的 relative path 目录下，并且在内存中将其重新可见。


**MergeTreeData::tryLoadPartsToAttach**

该函数检查磁盘上哪些 part 可以被 attach partition，并且在这些 part 的文件名前添加前缀 attaching_ 以防止被重复 attach。完成磁盘上的操作后，通过 createPart 函数，为这些 part 创建能够代表该 part 的内存数据结构。

```c++
MergeTreeData::MutableDataPartsVector MergeTreeData::tryLoadPartsToAttach(const ASTPtr & partition, bool attach_part,
        ContextPtr local_context, PartsTemporaryRename & renamed_parts)
{
    ...
    /// 遍历 detached/ 目录下的所有 part，找到 partition name 相同的 part
    ActiveDataPartSet active_parts(format_version);
    for (const auto & disk : disks)
    {
        for (auto it = disk->iterateDirectory(relative_data_path + source_dir); it->isValid(); it->next())
        {
            /// 10001_4_4_0
            const String & name = it->name();
            ...
            active_parts.add(name);
            name_to_disk[name] = disk;
        }
    }

    /// active_parts 记录了所有的可以被 attach 的 part 信息
    /// 需要将这些part在磁盘上的文件名 rename 成 attaching_xxxx，以避免重复 attch
    /// Inactive parts are renamed so they can not be attached in case of repeated ATTACH.
    /// name_to_disk 记录 part_name -> IDisk
    /// renamed_parts 记录了这些所有被 rename 过的 part 信息
    for (const auto & [name, disk] : name_to_disk)
    {
        const String containing_part = active_parts.getContainingPart(name);

        if (!containing_part.empty() && containing_part != name)
            // TODO maybe use PartsTemporaryRename here?
            disk->moveDirectory(relative_data_path + source_dir + name,
                relative_data_path + source_dir + "inactive_" + name);
        else
            renamed_parts.addPart(name, "attaching_" + name);
    }

    /// Try to rename all parts before attaching to prevent race with DROP DETACHED and another ATTACH.
    /// 给 detached 下所有目标 part 加前缀 attaching
    renamed_parts.tryRenameAll()

    ...
    ///
    MutableDataPartsVector loaded_parts;
    loaded_parts.reserve(renamed_parts.old_and_new_names.size());

    for (const auto & [old_name, new_name] : renamed_parts.old_and_new_names)
    {
        LOG_DEBUG(log, "Checking part {}", new_name);

        auto single_disk_volume = std::make_shared<SingleDiskVolume>("volume_" + old_name, name_to_disk[old_name]);
        MutableDataPartPtr part = createPart(old_name, single_disk_volume, source_dir + new_name);

        loadPartAndFixMetadataImpl(part);
        loaded_parts.push_back(part);
    }

    return loaded_parts;
}
```



loaded_parts
<img alt="picture 2" src="../../images/4531e2b5f505e86e0c9e1beefc56252f9f30a9341fc275ed742377924f698466.png" />  

renamed_parts

<img alt="picture 1" src="../../images/de8365b4507e246c89f3e389f53d795d1473fcb9ab55b0501f4a4683b0c65725.png" />  


**MergeTreeData::renameTempPartAndReplace**
```c++
bool MergeTreeData::renameTempPartAndReplace(
    MutableDataPartPtr & part, SimpleIncrement * increment, Transaction * out_transaction,
    std::unique_lock<std::mutex> & lock, DataPartsVector * out_covered_parts, MergeTreeDeduplicationLog * deduplication_log)
{
    ...
    part->assertState({DataPartState::Temporary});
    ...
    /// 确保 part 的 partition_id 与现有 partition 下 part 的 partition_id 相同
    if (DataPartPtr existing_part_in_partition = getAnyPartInPartition(part->info.partition_id, lock))
    {
        if (part->partition.value != existing_part_in_partition->partition.value)
            throw Exception(
                "Partition value mismatch between two parts with the same partition ID. Existing part: "
                + existing_part_in_partition->name + ", newly added part: " + part->name,
                ErrorCodes::CORRUPTED_DATA);
    }

    /// 更新 part 的 min & max block id 
    /** It is important that obtaining new block number and adding that block to parts set is done atomically.
      * Otherwise there is race condition - merge of blocks could happen in interval that doesn't yet contain new part.
      */
    if (increment)
    {
        part_info.min_block = part_info.max_block = increment->get();
        part_info.mutation = 0; /// it's equal to min_block by default
        part_name = part->getNewName(part_info);
    }
    else /// Parts from ReplicatedMergeTree already have names
        part_name = part->name;

}
```

## 其他线程
### ReplicatedMergeTreeRestartingThread
该对象构造时，在**全局的SchedulePool**中创建一个新的task。这个 task 有两个主要任务：
1. 进程启动/表刚创建时，对表进行初始化。包括启动必要线程、进行 leader 选举
2. Zookeeper Session Expired，典型如 XID Overflow 后，重建新的 session

对于初始化过程，执行的关键函数是 `tryStartup()`，tryStartUp 不仅需要处理初始化，还得处理重启以及过了一段时间后重新加入节点的情况，而后者其实是比较复杂的。
```c++
bool ReplicatedMergeTreeRestartingThread::tryStartup()
{
    ...
    /// 在 zk 记录自己的信息，如 ip:port 等
    activateReplica();

    /// 重启过程
    storage.cloneReplicaIfNeeded(zookeeper);

    storage.queue.load(zookeeper);

    /// pullLogsToQueue() after we mark replica 'is_active' (and after we repair if it was lost);
    /// because cleanup_thread doesn't delete log_pointer of active replicas.
    storage.queue.pullLogsToQueue(zookeeper);
    storage.queue.removeCurrentPartsFromMutations();
    storage.last_queue_update_finish_time.store(time(nullptr));
    ...
    /// 选主
    if (storage_settings->replicated_can_become_leader)
        storage.enterLeaderElection(); 

    storage.partial_shutdown_called = false;
    storage.partial_shutdown_event.reset();

    storage.queue_updating_task->activateAndSchedule();
    storage.mutations_updating_task->activateAndSchedule();
    storage.mutations_finalizing_task->activateAndSchedule();
    storage.cleanup_thread.start();
    storage.part_check_thread.start();

    return true;
}
```
值得注意的一点是，`enterLeaderElection`函数中如果自己成功充当主节点，那么则会启动`merge_selecting_task`，负责统一 merge 与 mutation 操作。
###  

###
`selectQueueEntry()`函数决定某条 log 是否可以被执行，如果 log 被该函数认为不应该执行（推迟执行），则其被推迟原因会被纪录在其内存状态中，我们在 system.replication_queue 查询到的某个 log 的 postpone_reason 就是在这里填写的。