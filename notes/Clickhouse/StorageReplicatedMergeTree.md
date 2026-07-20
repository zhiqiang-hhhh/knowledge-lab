[TOC]

## 代码版本

本文按本地 ClickHouse 代码整理：

- 代码目录：`/Users/roanhe/code/ClickHouse`
- 分支：`debug-25.3-dns-limit-repro`
- commit：`13341328f3f`

主要入口文件：

- `src/Storages/MergeTree/ReplicatedMergeTreeSink.cpp`
- `src/Storages/StorageReplicatedMergeTree.cpp`
- `src/Storages/MergeTree/ReplicatedMergeTreeQueue.cpp`
- `src/Storages/MergeTree/BackgroundJobsAssignee.cpp`
- `src/Storages/MergeTree/ReplicatedMergeTreeRestartingThread.cpp`
- `src/Core/ServerSettings.cpp`

## ReplicatedMergeTree 的主线

以一次 `INSERT INTO` 为主线，ReplicatedMergeTree 的写入和复制可以拆成五步：

1. sink 接收 chunk，把 block 按 partition 拆成一个或多个 part。
2. 当前 replica 在本地写临时 part。
3. 提交 part：分配 block number、写 dedup 节点、写 part 元信息、追加 replicated log。
4. 每个 replica 从全局 `/log` 拉取 log 到自己的 `/replicas/{replica}/queue`。
5. 后台 executor 从 queue 中选择可执行任务，执行 fetch、merge、mutation、drop、attach 等操作。

这个模型里有两个关键状态面：

- 本地磁盘和内存 working set：决定当前 replica 实际拥有哪些 part。
- Keeper/ZooKeeper 元数据：决定 replicated log、replica queue、block number、dedup、quorum 和 part 元信息。

ReplicatedMergeTree 的核心不是“严格按 queue 顺序执行”。queue 是每个 replica 对全局 log 的本地拷贝，真正执行时会根据依赖关系、future parts、drop range、fetch pool、merge strategy 等条件重排或 postpone。

## 写入路径要解决的问题

先不看代码细节，ReplicatedMergeTree 的写入可以用一个朴素模型理解：R1 写出一个 part X，随后把 X 注册到 Keeper/ZooKeeper；R2 看到 R1 拥有 X 后，通过 HTTP request 从 R1 fetch 这个 part。真正实现时，这条路径至少要解决几个一致性问题。

### 本地写 part 可能失败

R1 写 part X 到本地磁盘时，可能出现部分文件已经写成功、但最后的 `checksums.txt` 或元信息写失败的情况。如果一开始就把目录命名为正式 part 名 X，并提前放进 storage 目录和内存 working set，失败后很难安全回滚。尤其当后续 part Y 已经写入并参与查询或 merge 时，再删除 X 会让本地状态更复杂。

ClickHouse 的处理方式是先写临时目录，例如 `tmp_insert_...`。只有临时 part 内的数据、checksums、metadata 都完成并通过校验后，才用文件系统 rename 把临时目录改成正式 part 名，并把 part 加入内存元数据。这个过程对普通 MergeTree 和 ReplicatedMergeTree 都成立。

副本表还多了一层问题：本地 part 写完，不等于这个 part 已经可以对外作为复制事实存在。ReplicatedMergeTree 需要把本地 rename、内存 working set、Keeper 中的复制元数据放到一个提交协议里处理。

### Keeper 注册时可能发现冲突

假设 R1 本地已经写好了临时 part，但提交到 Keeper 时发现 R2 已经提交了同一个逻辑位置的 part。如果 R1 已经把 part 加入内存 working set，R1 和 R2 后续查询就可能看到不一致结果。

因此 ReplicatedMergeTree 不能直接沿用“本地 part 写完就 commit 到内存”的路径。它会先在 Keeper 的 partition 维度分配 block number：在 `block_numbers/{partition_id}` 下创建 `block-...` sequential 节点，由 Keeper 原子地给出全局递增序号。拿到 block number 后，R1 才能确定正式 part name，例如 `all_2_2_0`。

这个 block number 是 Keeper 分配的全局顺序，不依赖某个 replica 的本地状态，所以可以避免多个 replica 在同一 partition 内生成冲突的 part 版本。另一方面，如果某次写入拿到了 block number 但后续提交失败，这个序号不会被实际 part 使用，因此 part name 中的 block number 可以不连续。

### 副本之间需要交换 part

R1 成功提交 part 后，R2 并不会自动知道本地该 fetch 什么。R1 需要在 Keeper 中写入一组复制元数据，典型包括：

```txt
create /log/log-
delete /block_numbers/all/block-0000000002
create /blocks/all_1513...
create /replicas/node1/parts/all_2_2_0
check /clickhouse/sessions/...
```

这些操作的含义分别是：

- `/log/log-...`：追加 replicated log，告诉其他 replica 有新的 part。
- `/block_numbers/.../block-...`：释放 block number lock，避免 Keeper 节点无限膨胀。
- `/blocks/{block_id}`：记录 insert dedup block id。
- `/replicas/node1/parts/all_2_2_0`：记录 node1 拥有这个 part。
- session check：确认提交时当前 replica 的 Keeper session 仍然有效。

`/log/log-...` 的内容类似 `GET_PART all_2_2_0 from node1`。其他 replica 拉取这条 log 到自己的 queue 后，就知道可以从 node1 fetch `all_2_2_0`。`block_numbers` 下的 sequential 节点删除后不会导致序号复用；Keeper sequential counter 继续向前增长。

### 需要防止重复写入

同一个 `INSERT` 可能因为客户端重试、网络超时、分布式写入转发重发等原因执行多次。如果每次都生成新 part，用户会看到重复数据。

ReplicatedMergeTree 会为写入 block 计算 dedup block id，并在 Keeper 的 `blocks/{block_id}` 下记录。再次写入相同 block 时，创建同名 `blocks` 节点会发现已经存在，上层把这次写入视为 deduplicated，不再提交新 part。

实际代码里还有一个优化：dedup 检查会和创建 block number sequential node 放在同一个 Keeper 原子操作里。如果发现 `blocks/{block_id}` 已存在，就不会浪费一次 block number 分配。

### 需要元数据对账

R1 完成提交后，仍然可能因为磁盘故障、误删、重启恢复等原因丢失本地 part。如果 R1 不知道自己缺了数据，后续查询落到 R1 和其他 replica 上就会不一致。

所以每个 replica 会在 Keeper 的 `/replicas/{replica}/parts/{part}` 下登记自己应该拥有的 part。启动、恢复或检查时，replica 可以把本地磁盘和 Keeper 中“自己应该拥有的 part”进行对账。如果发现本地缺失，会进入恢复路径：降低自身可用状态，检查其他 replica 在 Keeper 中登记的 part 信息，并尝试从仍然拥有该 part 的 replica fetch 回来。

这些问题对应到后面的源码路径：临时 part 和本地 rename 在写入入口与 `commitPart` 中处理；block number 和 dedup 在 `allocateBlockNumber` 中处理；复制通知通过 `/log` 和 replica queue 处理；本地和 Keeper part 元信息对账则由启动恢复、part check 和 fetch 逻辑共同完成。

## 写入入口

当前写入入口是 `ReplicatedMergeTreeSinkImpl<async_insert>::consume(Chunk & chunk)`。普通 insert 和 async insert 使用同一个模板类，差异主要在 block id 计算、async insert 内部去重和冲突重写。

主流程可以概括为：

```c++
void ReplicatedMergeTreeSinkImpl<async_insert>::consume(Chunk & chunk)
{
    auto block = getHeader().cloneWithColumns(chunk.getColumns());

    auto zookeeper = ZooKeeperWithFaultInjection::createInstance(...);
    size_t replicas_num = checkQuorumPrecondition(zookeeper);

    auto part_blocks = MergeTreeDataWriter::splitBlockIntoParts(
        std::move(block), max_parts_per_block, metadata_snapshot, context, async_insert_info);

    for (auto & current_block : part_blocks)
    {
        auto temp_part = storage.writer.writeTempPart(current_block, metadata_snapshot, context);
        if (!temp_part.part)
            continue;

        BlockIDsType block_id;
        if constexpr (async_insert)
            block_id = AsyncInsertBlockInfo::getHashesForBlocks(...);
        else if (deduplicate)
            block_id = temp_part.part->getNewPartBlockID(block_dedup_token);

        partitions.emplace_back(...);
    }

    finishDelayedChunk(zookeeper);
}
```

这里有几个关键点：

- `checkQuorumPrecondition` 在写临时 part 前执行。quorum insert 会检查活跃 replica 数和前一个 quorum part 状态。
- `splitBlockIntoParts` 负责按 partition 拆分 block；一个 chunk 可能生成多个 part。
- 普通 insert 的 dedup block id 来自 `part->getNewPartBlockID(block_dedup_token)`。
- 如果 chunk 没有显式 dedup token，sink 会通过 `DeduplicationToken::TokenInfo` 收集 chunk hash，供后续定义 token。
- 临时 part 可以延迟 finalize。`finishDelayedChunk` 统一 finalize 并提交，配合 parallel write 场景关闭 stream。

普通 insert 的 `finishDelayedChunk` 主路径：

```c++
for (auto & partition : delayed_chunk->partitions)
{
    partition.temp_part.finalize();
    auto & part = partition.temp_part.part;

    bool deduplicated = commitPart(
        zookeeper, part, partition.block_id, delayed_chunk->replicas_num).second;

    if (!deduplicated)
        partition.temp_part.prewarmCaches();

    PartLog::addNewPart(...);
    StorageReplicatedMergeTree::incrementInsertedPartsProfileEvent(part->getType());
}
```

async insert 在提交时还会处理同一个 async block 内部的冲突。遇到 Keeper 中已有 block id 时，会刷新 `async_block_ids_cache`，过滤冲突行，重写临时 part，再重试提交。

## commitPart

`commitPart` 是写入路径的核心。它同时处理 block number、dedup、replicated log、本地 rename 和 Keeper multi。

正常路径可以概括为：

```c++
auto block_number_lock = storage.allocateBlockNumber(
    part->info.partition_id, zookeeper, block_id_path);

if (!block_number_lock.has_value())
    return CommitRetryContext::DUPLICATED_PART;

auto block_number = block_number_lock->getNumber();
part->info.min_block = block_number;
part->info.max_block = block_number;
part->setName(part->getNewName(part->info));

Coordination::Requests ops;

get_logs_ops(ops);
block_number_lock->getUnlockOp(ops);
get_quorum_ops(ops);
storage.getLockSharedDataOps(*part, zookeeper, false, {}, ops);
storage.getCommitPartOps(ops, part, block_id_path);

MergeTreeData::Transaction transaction(storage, NO_TRANSACTION_RAW);

{
    auto lock = storage.lockParts();
    storage.renameTempPartAndAdd(part, transaction, lock, true);
}

transaction.renameParts();

auto multi_code = zookeeper->tryMultiNoThrow(
    ops, responses, /* check_session_valid */ true);

if (multi_code == Coordination::Error::ZOK)
{
    part->new_part_was_committed_to_zookeeper_after_rename_on_disk = true;
    transaction.commit();
    block_number_lock->assumeUnlocked();
    return CommitRetryContext::SUCCESS;
}
```

实际提交顺序是：

1. `allocateBlockNumber` 在 partition 维度分配 block number，同时做 dedup 检查。
2. 根据 block number 设置 part name。
3. 准备 Keeper multi ops：写 log、释放 block number lock、写 quorum 状态、写 shared data lock、写 part 元信息、写 dedup block 节点。
4. 本地把临时 part rename 到正式目录，并加入 working set 事务。
5. 提交 Keeper multi。
6. Keeper 成功后提交本地事务。

`commitPart` 带有 `CommitRetryContext`。如果 Keeper 返回硬错误或连接异常，提交结果可能处于未知状态。代码会尝试恢复提交状态；无法立即确认时，会把本地 part 放入检查路径，后续由 part check/恢复逻辑确认该 part 应该保留还是删除。

这个顺序的重点是：本地 rename 发生在 Keeper multi 之前，但本地事务只有在 Keeper 成功后才正式 commit。这样可以把本地文件操作纳入事务语义，同时用 Keeper multi 保证复制元数据的一致性。

## block number 和 dedup

`StorageReplicatedMergeTree::allocateBlockNumber` 使用 `block_numbers/{partition_id}` 下的 ephemeral sequential 节点分配 block number。

核心逻辑：

```c++
String block_numbers_path = fs::path(zookeeper_table_path) / "block_numbers";
String partition_path = fs::path(block_numbers_path) / partition_id;

if (!existsNodeCached(zookeeper, partition_path))
{
    Coordination::Requests ops;
    ops.push_back(zkutil::makeCheckRequest(fs::path(replica_path) / "host", -1));
    ops.push_back(zkutil::makeCreateRequest(partition_path, "", zkutil::CreateMode::Persistent));
    ops.push_back(zkutil::makeSetRequest(block_numbers_path, "", -1));
    ...
}

return createEphemeralLockInZooKeeper(
    fs::path(partition_path) / "block-",
    fs::path(zookeeper_table_path) / "temp",
    zookeeper,
    zookeeper_block_id_path,
    std::nullopt);
```

关键状态：

- `block_numbers/{partition_id}/block-...`：partition 内递增 block number。
- `blocks/{block_id}`：insert dedup 节点。
- `temp/abandonable_lock-*`：block number lock 的辅助节点，用来支持安全释放或放弃。

如果 `zookeeper_block_id_path` 已存在，说明该 block 已经提交过，`allocateBlockNumber` 返回空值。上层把这次 insert 记为 deduplicated，不会提交新 part。

创建 partition 节点时，代码会在同一个 Keeper transaction 里检查当前 replica 的 `host` 节点、创建 partition path，并 `set block_numbers`。注释说明这里借父节点版本变化来检查 partition 集合变化，因为 Keeper 没有 `CheckChildren` 语义。

## replicated log 到 replica queue

写入成功后，全局 `/log/log-...` 中会出现一条 `GET_PART` log。每个 replica 通过 `queueUpdatingTask` 调用 `ReplicatedMergeTreeQueue::pullLogsToQueue`，把全局 log 拷贝到自己的 queue。

当前签名：

```c++
std::pair<int32_t, int32_t> ReplicatedMergeTreeQueue::pullLogsToQueue(
    zkutil::ZooKeeperPtr zookeeper,
    Coordination::WatchCallback watch_callback,
    PullLogsReason reason)
```

返回值是 `{log_znode_version, mutations_version}`。

主流程：

```c++
std::lock_guard lock(pull_logs_to_queue_mutex);

String index_str = zookeeper->get(fs::path(replica_path) / "log_pointer");

Coordination::Stat stat;
zookeeper->get(fs::path(zookeeper_path) / "log", &stat);

Strings log_entries = zookeeper->getChildrenWatch(
    fs::path(zookeeper_path) / "log", nullptr, watch_callback);

int32_t mutations_version = updateMutations(zookeeper);

if (index_str.empty())
{
    index = log_entries.empty() ? 0 : parse<UInt64>(
        std::min_element(log_entries.begin(), log_entries.end())->substr(strlen("log-")));
    zookeeper->set(fs::path(replica_path) / "log_pointer", toString(index));
}
else
{
    index = parse<UInt64>(index_str);
}

std::erase_if(log_entries, [&min_log_entry](const String & entry) {
    return entry < min_log_entry;
});
```

随后按 batch 复制：

```c++
Strings get_paths;
for (auto it = begin; it != end; ++it)
    get_paths.emplace_back(fs::path(zookeeper_path) / "log" / *it);

auto get_results = zookeeper->get(get_paths);

for (...)
{
    copied_entries.emplace_back(LogEntry::parse(res.data, res.stat, format_version));

    ops.emplace_back(zkutil::makeCreateRequest(
        fs::path(replica_path) / "queue/queue-",
        res.data,
        zkutil::CreateMode::PersistentSequential));

    if (entry.type == LogEntry::GET_PART || entry.type == LogEntry::ATTACH_PART)
        update min_unprocessed_insert_time;
}

ops.emplace_back(zkutil::makeSetRequest(
    fs::path(replica_path) / "log_pointer", toString(last_entry_index + 1), -1));

auto responses = zookeeper->multi(ops, /* check_session_valid */ true);

std::lock_guard state_lock(state_mutex);
insertUnlocked(copied_entry, unused, state_lock);

merge_strategy_picker.refreshState();
```

完成一批复制后会触发：

```c++
storage.background_operations_assignee.trigger();
```

需要注意：

- `pull_logs_to_queue_mutex` 保证同一 replica 上同时只有一个线程拉取 log。
- `log_pointer` 表示当前 replica 已拉取到的全局 log 位置。
- `queue/queue-...` 是 persistent sequential 节点，记录本 replica 对某条 log 的执行状态。
- `GET_PART` 和 `ATTACH_PART` 会更新 `min_unprocessed_insert_time`。
- 每批插入内存 queue 后会刷新 `merge_strategy_picker` 状态。

诊断时可以关注两条日志：

```txt
Pulling N entries to queue: log-... - log-...
Pulled N entries to queue.
```

两条日志之间的耗时包含：列出 `/log` 子节点、批量读取 log 内容、创建本 replica queue 节点、更新 `log_pointer`、更新内存 queue。

## 后台任务模型

ReplicatedMergeTree 构造函数会创建几个 `BackgroundSchedulePoolTaskHolder`：

```c++
queue_updating_task = getContext()->getSchedulePool().createTask(
    "... queueUpdatingTask", [this]{ queueUpdatingTask(); });

mutations_updating_task = getContext()->getSchedulePool().createTask(
    "... mutationsUpdatingTask", [this]{ mutationsUpdatingTask(); });

merge_selecting_task = getContext()->getSchedulePool().createTask(
    "... mergeSelectingTask", [this] { mergeSelectingTask(); });

mutations_finalizing_task = getContext()->getSchedulePool().createTask(
    "... mutationsFinalizingTask", [this] { mutationsFinalizingTask(); });
```

这些 task 属于全局 `BackgroundSchedulePool`，负责轻量调度工作，不直接执行大 fetch 或 merge。

当前 `ServerSettings.cpp` 中的默认值：

- `background_pool_size`: 16
- `background_fetches_pool_size`: 16
- `background_schedule_pool_size`: 512

`programs/server/config.xml` 示例配置里写着 16/8/128，以 server setting 声明为默认值来源。

真正的数据处理通过 `MergeTreeData::background_operations_assignee` 分发。`MergeTreeData` 构造时会创建自己的 `BackgroundJobsAssignee`，所以可以理解为每个 MergeTree 表对象都有一个用于 data processing 的调度 helper：

```c++
MergeTreeData::MergeTreeData(...)
    : ...
    , background_operations_assignee(
        *this, BackgroundJobsAssignee::Type::DataProcessing, getContext())
{
    ...
}
```

`BackgroundJobsAssignee` 本身不执行 fetch、merge 或 mutation。它只是把“这个表需要再调度一次后台数据处理”的信号投到 `BackgroundSchedulePool`。

`BackgroundJobsAssignee::trigger()`：

```c++
void BackgroundJobsAssignee::trigger()
{
    std::lock_guard lock(holder_mutex);
    if (!holder)
        return;

    no_work_done_count /= 2;
    holder->schedule();
}
```

`BackgroundJobsAssignee::threadFunc()` 是被 SchedulePool 执行的轻量调度函数。它回调具体表的 data processing 逻辑；如果没有成功分发出实际任务，就 postpone 自己：

```c++
void BackgroundJobsAssignee::threadFunc()
{
    bool succeed = false;
    switch (type)
    {
        case Type::DataProcessing:
            succeed = data.scheduleDataProcessingJob(*this);
            break;
        case Type::Moving:
            succeed = data.scheduleDataMovingJob(*this);
            break;
    }

    if (!succeed)
        postpone();
}
```

`StorageReplicatedMergeTree::scheduleDataProcessingJob` 从 replication queue 选择一条可执行 entry，再按类型分发到不同 executor：

```c++
cleanup_thread.wakeupEarlierIfNeeded();

if (queue.actions_blocker.isCancelled())
    return false;

ReplicatedMergeTreeQueue::SelectedEntryPtr selected_entry = selectQueueEntry();
if (!selected_entry)
    return false;

auto job_type = selected_entry->log_entry->type;

if (job_type == LogEntry::GET_PART || job_type == LogEntry::ATTACH_PART)
    assignee.scheduleFetchTask(... processQueueEntry ...);
else if (job_type == LogEntry::MERGE_PARTS)
    assignee.scheduleMergeMutateTask(std::make_shared<MergeFromLogEntryTask>(...));
else if (job_type == LogEntry::MUTATE_PART)
    assignee.scheduleMergeMutateTask(std::make_shared<MutateFromLogEntryTask>(...));
else
    assignee.scheduleCommonTask(... processQueueEntry ...);
```

对应 executor 来自全局 context：

- `getMergeMutateExecutor()`
- `getFetchesExecutor()`
- `getCommonExecutor()`
- `getMovesExecutor()`

因此 `BackgroundSchedulePoolTask` 不能理解为真正执行 merge/fetch 的线程数。SchedulePool 是调度入口，fetch、merge、mutation、common task 在各自 `MergeTreeBackgroundExecutor` 中执行。

`MergeTreeBackgroundExecutor` 构造时会创建一个 `ThreadPool`，并按 `threads_count` 启动常驻 worker：

```c++
MergeTreeBackgroundExecutor::MergeTreeBackgroundExecutor(
    String name_,
    size_t threads_count_,
    size_t max_tasks_count_,
    CurrentMetrics::Metric metric_,
    ...)
    : name(name_)
    , threads_count(threads_count_)
    , max_tasks_count(max_tasks_count_)
    , metric(metric_)
    , pool(std::make_unique<ThreadPool>(...))
{
    pending.setCapacity(max_tasks_count);
    active.set_capacity(max_tasks_count);

    pool->setMaxThreads(std::max(1UL, threads_count));
    pool->setMaxFreeThreads(std::max(1UL, threads_count));
    pool->setQueueSize(std::max(1UL, threads_count));

    for (size_t number = 0; number < threads_count; ++number)
        pool->scheduleOrThrowOnError([this] { threadFunction(); });
}
```

每个 worker 进入 `threadFunction()` 的无限循环，从 `pending` 队列取任务，放入 `active`，然后调用 `routine()`：

```c++
void MergeTreeBackgroundExecutor::threadFunction()
{
    while (true)
    {
        TaskRuntimeDataPtr item;
        {
            std::unique_lock lock(mutex);
            has_tasks.wait(lock, [this] { return !pending.empty() || shutdown; });

            if (shutdown)
                break;

            item = std::move(pending.pop());
            active.push_back(item);
        }

        routine(std::move(item));
    }
}
```

`trySchedule` 只是把 `ExecutableTask` 包成 runtime data 放进 `pending`，并用 executor 对应的 metric 判断是否超过 `max_tasks_count`：

```c++
bool MergeTreeBackgroundExecutor::trySchedule(ExecutableTaskPtr task)
{
    std::lock_guard lock(mutex);

    if (shutdown)
        return false;

    auto & value = CurrentMetrics::values[metric];
    if (value.load() >= static_cast<int64_t>(max_tasks_count))
        return false;

    pending.push(std::make_shared<TaskRuntimeData>(std::move(task), metric));
    has_tasks.notify_one();
    return true;
}
```

真正执行一步任务发生在 `routine()`：

```c++
bool need_execute_again = item->task->executeStep();

if (!need_execute_again)
{
    complete_task(std::move(item));
    return;
}

restart_task(std::move(item));
```

这里的 `executeStep()` 返回值决定 task 是完成，还是重新进入 executor 等下一轮执行。对 RMT 来说，queue 选择逻辑先决定当前 replica 是否应该执行某个 log entry；随后 `BackgroundJobsAssignee` 只负责按 entry 类型把 task 投递到 fetch、merge/mutate 或 common executor。

`system.metrics` 中的 `MergeTreeBackgroundExecutorThreads` 来自 executor 内部 `ThreadPool` 的线程指标，用来观察采样时刻 MergeTree background executor 的线程数量；具体 fetch/merge 是否拥塞，还要结合对应 executor 的 task metric 和 `system.replication_queue` 的 postpone 信息。

## queue entry 选择

`ReplicatedMergeTreeQueue::selectEntryToProcess` 决定当前 replica 下一步执行哪条 queue entry。

核心逻辑：

```c++
ReplicatedMergeTreeQueue::SelectedEntryPtr ReplicatedMergeTreeQueue::selectEntryToProcess(...)
{
    std::unique_lock lock(state_mutex);

    for (auto it = queue.begin(); it != queue.end(); ++it)
    {
        if ((*it)->currently_executing)
            continue;

        if (shouldExecuteLogEntry(**it, (*it)->postpone_reason, merger_mutator, data, lock))
        {
            entry = *it;
            queue.splice(queue.end(), queue, it);
            break;
        }

        ++(*it)->num_postponed;
        (*it)->last_postpone_time = time(nullptr);
    }

    if (entry)
        return std::make_shared<SelectedEntry>(
            entry,
            std::unique_ptr<CurrentlyExecuting>{new CurrentlyExecuting(entry, *this, lock)});

    return {};
}
```

行为要点：

- 一次只选择一条可执行 entry。
- 正在执行的 entry 会被跳过。
- 可执行 entry 被选中后会移动到 queue 尾部。
- 不可执行 entry 会更新 `num_postponed` 和 `last_postpone_time`。
- `SelectedEntry` 持有 `CurrentlyExecuting`，在生命周期内维护 `currently_executing` 和 `future_parts`。

`shouldExecuteLogEntry` 的主要 postpone 条件：

1. 当前 entry 生成的 virtual part 被正在执行的 future part 覆盖。
2. 当前 entry 和 DROP/REPLACE intent 相交。
3. 非 DROP entry 受 `DROP_PART` 影响。
4. 将要生成的 part 已经落在未来会被 drop 的范围里。
5. `GET_PART` 或 `ATTACH_PART` 不能通过 `canExecuteFetch`。
6. `MERGE_PARTS` 或 `MUTATE_PART` 在 merges/mutations 被取消时不能执行。
7. merge/mutate 的 source part 正在 `future_parts` 中。
8. TTL merge 数量、source parts size、merge strategy picker 等限制不满足。

这些 postpone 原因最终体现在 `system.replication_queue.postpone_reason`。

## fetch 条件

`StorageReplicatedMergeTree::canExecuteFetch` 决定 `GET_PART` 或 fallback fetch 当前能不能执行：

```c++
bool StorageReplicatedMergeTree::canExecuteFetch(
    const ReplicatedMergeTreeLogEntry & entry,
    String & disable_reason) const
{
    if (fetcher.blocker.isCancelled())
        return false;

    auto replicated_fetches_pool_size = getContext()->getFetchesExecutor()->getMaxTasksCount();
    size_t busy_threads_in_pool =
        CurrentMetrics::values[CurrentMetrics::BackgroundFetchesPoolTask].load(...);

    if (busy_threads_in_pool >= replicated_fetches_pool_size)
        return false;

    if (replicated_fetches_throttler->isThrottling())
        return false;

    if (entry.source_replica.empty())
    {
        auto part = getPartIfExists(entry.new_part_name, {Active, Outdated, Deleting});
        if (part && part->was_removed_as_broken)
        {
            cleanup_thread.wakeup();
            return false;
        }
    }

    return true;
}
```

fetch 可能被推迟的常见原因：

- `fetcher.blocker` 已取消 replicated fetch。
- `BackgroundFetchesPoolTask` 已达到 `getFetchesExecutor()->getMaxTasksCount()`。
- replicated fetches throttler 正在限速。
- 本地存在同名 broken part，等待 cleanup thread 清理。

fetch pool 上限来自 `getContext()->getFetchesExecutor()->getMaxTasksCount()`，运行时诊断时应结合当前 executor 配置和 `BackgroundFetchesPoolTask` 指标看。

## executeLogEntry

普通 queue entry 通过 `processQueueEntry` 进入：

```c++
return queue.processEntry([this]{ return getZooKeeper(); }, entry, [&](LogEntryPtr & entry_to_process)
{
    return executeLogEntry(*entry_to_process);
});
```

merge/mutate 是例外。`scheduleDataProcessingJob` 已经把它们分发给：

- `MergeFromLogEntryTask`
- `MutateFromLogEntryTask`

所以 `executeLogEntry` 中遇到 `MERGE_PARTS` 或 `MUTATE_PART` 会抛 `LOGICAL_ERROR`，防止走错执行路径。

`executeLogEntry` 主要处理：

- `DROP_RANGE` / `DROP_PART`: `executeDropRange`
- `REPLACE_RANGE`: `executeReplaceRange`
- `GET_PART`: `executeFetch`
- `ATTACH_PART`: 先尝试本地 attach，失败再 fetch
- `ALTER_METADATA`: `executeMetadataAlter`
- `SYNC_PINNED_PART_UUIDS`
- `CLONE_PART_FROM_SHARD`

对 `GET_PART`、`ATTACH_PART`、`MERGE_PARTS`、`MUTATE_PART`，执行前都会先检查本地是否已经有目标 part 或 covering part，并且 Keeper 中 `replica_path/parts/{part}` 存在。如果存在，当前 entry 可以直接跳过。

`executeFetch` 会先找拥有 covering part 的 replica：

```c++
bool StorageReplicatedMergeTree::executeFetch(LogEntry & entry, bool need_to_check_missing_part)
{
    String replica = findReplicaHavingCoveringPart(entry, true);
    auto metadata_snapshot = getInMemoryMetadataPtr();
    ...
}
```

如果 quorum part 没有活跃 replica 拥有，代码会尝试把 quorum 标记为失败，并维护 `/quorum/failed_parts` 以及 dedup `blocks` 节点。

`queue.processEntry` 中的执行函数返回 true 后，会调用 `removeProcessedEntry` 删除本 replica queue 下的 `queue-...` 节点。

## DROP PARTITION / DROP PART

DROP 类操作在 replication log 中表现为 `DROP_RANGE` 或 `DROP_PART`。每个 replica 消费 log 时执行 `executeDropRange`。

核心行为：

- `queue.removePartProducingOpsInRange` 清理范围内会产生 part 的 queue 操作。
- `removePartsInRangeFromWorkingSet` 把命中的 part 从 working set 移除，并设置 `remove_time`。
- 如果是 detach，则把 part clone 到 `detached/`。
- `tryRemovePartsFromZooKeeperWithRetries` 删除 Keeper 中的 part 元信息。
- 唤醒 cleanup thread 尽快清理磁盘 old parts。

cleanup thread 周期调用 `clearOldPartsAndRemoveFromZK()`，进一步执行：

- `grabOldParts()`
- `removePartsFromFilesystem(...)`
- `removePartsFinally(...)`
- `removePartsFromZooKeeper(...)`

old part 能否最终清理，主要取决于 `remove_time` 和 refcount。

## ATTACH PARTITION

`ATTACH PARTITION` 的处理思路是：优先在本地找到可 attach 的 part，找不到再 fetch。

对 `ATTACH_PART` entry：

1. `executeLogEntry` 先检查本地是否已经有目标 part 或 covering part。
2. 如果没有，调用 `attachPartHelperFoundValidPart(entry)` 尝试在本地 `detached/` 或现有路径找到有效 part。
3. 找到后走本地 transaction：

```c++
Transaction transaction(*this, NO_TRANSACTION_RAW);
part->version.setCreationTID(Tx::PrehistoricTID, nullptr);
renameTempPartAndReplace(part, transaction, /*rename_in_transaction=*/ true);
transaction.renameParts();
checkPartChecksumsAndCommit(transaction, part, {}, /*replace_zero_copy_lock*/ true);
```

4. 如果本地找不到有效 part，则作为 fetch 处理，从其他 replica 下载。

## RestartingThread

`ReplicatedMergeTreeRestartingThread` 负责 replica 启动、Keeper session 重建和队列恢复。

启动主路径中的关键动作：

```c++
activateReplica();
storage.cloneReplicaIfNeeded(zookeeper);
storage.queue.load(zookeeper);
storage.queue.pullLogsToQueue(zookeeper, {}, ReplicatedMergeTreeQueue::LOAD);
storage.queue.removeCurrentPartsFromMutations();

if (storage_settings->replicated_can_become_leader)
    storage.enterLeaderElection();

storage.queue_updating_task->activateAndSchedule();
storage.mutations_updating_task->activateAndSchedule();
storage.mutations_finalizing_task->activateAndSchedule();
storage.cleanup_thread.start();
storage.part_check_thread.start();
storage.background_operations_assignee.start();
```

leader replica 会激活 `merge_selecting_task`，负责选择 merge/mutation 并写入 replicated log。非 leader replica 不主动选择 replicated merge，但会消费 log 中已有的 merge/mutate 任务。

## 排查关注点

### queue 拉取慢

关注日志：

```txt
Pulling N entries to queue: log-... - log-...
Pulled N entries to queue.
```

如果间隔大，优先看：

- Keeper `getChildrenWatch(/log)` 返回节点数是否过多。
- 批量 `get(log paths)` 是否慢。
- `multi(create queue nodes + set log_pointer)` 是否慢。
- 内存 queue 更新是否异常。

### GET_PART 长期 postpone

优先看 `system.replication_queue.postpone_reason`。常见方向：

- replicated fetches 被 `fetcher.blocker` 取消。
- `BackgroundFetchesPoolTask >= getFetchesExecutor()->getMaxTasksCount()`。
- fetch 被 `max_replicated_fetches_network_bandwidth` 或 server 级 fetch bandwidth throttler 限制。
- 本地同名 broken part 还没清理。
- 目标 part 被 future part 覆盖，等待另一个正在执行的 entry 完成。

### MERGE_PARTS / MUTATE_PART 长期 postpone

常见方向：

- source part 正在被其他 queue entry fetch/merge/mutate，存在于 `future_parts`。
- merges/mutations 被 blocker 取消。
- TTL merge 并发超过限制。
- source parts size 超过当前允许的 `max_source_parts_size`。
- shared merge strategy 选择了其他 replica 执行，当前 replica 等待对方完成。

### 背景线程指标

常用指标：

- `BackgroundSchedulePoolTask`：SchedulePool 中活跃轻量任务数。
- `BackgroundFetchesPoolTask`：fetch executor 当前任务数。
- `system.replication_queue`：queue entry 状态、重试次数、postpone 原因。
- `system.merges`：正在执行的 merge/mutation。

诊断时要区分调度线程和执行线程。`BackgroundSchedulePool` 负责触发和周期任务；fetch、merge、mutation 的实际执行在对应 executor 中完成。
