# ReplicatedMergeTree Part 提交与重试

接 [[ParallelStream]]：part 写盘只完成了「数据落地」。对于 `ReplicatedMergeTree`，还要把 part **提交到 ZooKeeper**（抢 block number、写去重节点、达成 quorum）。这一篇讲 `finishDelayedChunk → commitPart → ZooKeeperRetriesControl` 这条提交+重试链路。

## 1. 两种 sink：finishDelayedChunk 的 `<false>` 与 `<true>`

`ReplicatedMergeTreeSinkImpl<async_insert>` 按模板参数分两套（`ReplicatedMergeTreeSink.h`）：

```cpp
using ReplicatedMergeTreeSink                     = ReplicatedMergeTreeSinkImpl<false>; // 普通同步 insert
using ReplicatedMergeTreeSinkWithAsyncDeduplicate = ReplicatedMergeTreeSinkImpl<true>;  // async insert + async dedup
```

`StorageReplicatedMergeTree::write` 决定用哪套：

```cpp
bool async_deduplicate = async_insert && async_insert_deduplicate
                       && replicated_deduplication_window_for_async_inserts != 0
                       && insert_deduplicate;
if (async_deduplicate) return ReplicatedMergeTreeSinkWithAsyncDeduplicate(...);  // <true>
return ReplicatedMergeTreeSink(...);                                            // <false>
```

| insert 类型 | sink | finishDelayedChunk 特化 |
|---|---|---|
| 普通同步 INSERT | `<false>` | `<false>` |
| async insert + async dedup | `<true>` | `<true>` |

> 即：普通 insert 走 `<false>::finishDelayedChunk`，**不会**进 `<true>` 那个特化。只有 `async_insert=1`（且 dedup 条件满足）才走 `<true>`。

`finishDelayedChunk` 在 `consume()`（攒批/结尾）和 `onFinish()` 里被调用，对每个攒下的 part 做 `finalize()` + `commitPart()`：

```cpp
void finishDelayedChunk(zookeeper) {
    if (!delayed_chunk) return;
    for (partition : delayed_chunk->partitions) {
        partition.temp_part.finalize();                 // 真正落盘（见 [[ParallelStream]]）
        commitPart(zookeeper, part, block_id, replicas_num);  // 提交 ZK / 去重 / quorum
        PartLog::addNewPart(...);
    }
    delayed_chunk.reset();
}
```

## 2. commitPart 的状态机

`commitPart` 用一个 `retryLoop` 驱动状态机，stage 记录"重试时该从哪一步继续"：

```cpp
enum Stage { LOCK_AND_COMMIT, DUPLICATED_PART, SUCCESS, ERROR };

auto stage_switcher = [&]{
    try {
        switch (retry_context.stage) {
            case LOCK_AND_COMMIT:  retry_context.stage = commit_new_part_stage();  break; // 抢 block number + 提交
            case DUPLICATED_PART:  retry_context.stage = resolve_duplicate_stage(); break; // 处理去重命中
            case SUCCESS / ERROR:  throw LOGICAL_ERROR;
        }
    }
    catch (const KeeperException &) { throw; }           // 硬件错误：原样抛给 retryLoop
    catch (DB::Exception &) { retry_context.stage = ERROR; throw; }
};

retries_ctl.retryLoop([&]{
    zookeeper->setKeeper(storage.getZooKeeper());
    while (true) {
        auto prev = retry_context.stage;
        stage_switcher();
        if (prev == retry_context.stage) return;                  // stage 没推进 → 交回 retryLoop（通常因为 set 了 error）
        if (stage == SUCCESS || stage == ERROR) return;           // 完成
    }
});
```

- `commit_new_part_stage`：抢 `block_numbers/.../block-`，写 `blocks/<block_id>` 去重节点。若去重节点已存在 → stage 转 `DUPLICATED_PART`；成功 → `SUCCESS`。
- `resolve_duplicate_stage`：取已存在 part 名，置 `part_was_deduplicated=true`，记 `Block ... already exists ... ignoring it`，stage 转 `SUCCESS`。

## 3. ZooKeeperRetriesControl：怎么判断要不要重试

核心是一个标志 `iteration_succeeded`，**不看 stage、不看返回值**（`ZooKeeperRetries.h`）：

```cpp
void retryLoop(f) {
    current_iteration = 0; current_backoff_ms = initial_backoff_ms;
    while (current_iteration == 0 || canTry()) {
        iteration_succeeded = true;          // 每轮乐观假设成功
        try { f(); }
        catch (const KeeperException & e) {
            if (!isHardwareError(e.code)) throw;   // 非硬件错误 → 抛出，不重试
            setKeeperError(...);             // 硬件错误 → iteration_succeeded=false, total_failures++
        }
        catch (...) { throw; }               // 其他异常 → 抛出，不重试
        ++current_iteration;
    }
}

bool canTry() {                              // 下一轮开头判定
    if (iteration_succeeded)              return false;   // 成功 → 退出（不重试）
    if (stop_retries)                  { throw; }
    if (total_failures > max_retries)  { throw; }         // 超限 → 抛最后的错误
    query_status->checkTimeLimit();
    sleepForMilliseconds(current_backoff_ms);             // 指数退避
    current_backoff_ms = min(current_backoff_ms*2, max_backoff_ms);
    return true;                                          // 重试
}
```

`iteration_succeeded` 变 false 只有两条路径：

1. **`f()` 抛硬件类 `KeeperException`**（连接断开/超时/session 过期）→ 被捕获 → `setKeeperError`。非硬件 Keeper 错误（`ZNODEEXISTS` 等）视作语义响应，直接 rethrow，**不重试**。
2. **`f()` 内显式 `setUserError`/`setKeeperError`** —— 调用方主动反馈失败。

> 例（表只读）：`commit_new_part_stage` 调 `retries_ctl.setUserError(TABLE_IS_READ_ONLY)` 后 **return 同一个 stage**。于是内层 `while` 因 `prev==stage` return，但 `iteration_succeeded` 已为 false → `canTry()` 退避后重试。这就是注释"stage 没推进 → 触发重试"的真实含义：**stage 没推进通常意味着刚 set 了 error**；若既没推进也没 set error，则当成功退出，不重试。

`current_backoff_ms`：指数退避的 sleep 时长。`initial → ×2 → … → 封顶 max_backoff_ms`，只在 `canTry()` 决定重试那条路径上消费；退避 sleep 前后各做一次 `checkTimeLimit()` 以响应查询取消。

## 4. 一句话总结

普通同步 insert 走 `<false>::finishDelayedChunk`，对每个 part `finalize()` 后用 `commitPart` 提交 ZK；`commitPart` 用 `LOCK_AND_COMMIT → (DUPLICATED_PART) → SUCCESS/ERROR` 状态机记录进度，外层 `ZooKeeperRetriesControl::retryLoop` **只凭 `iteration_succeeded`（硬件 Keeper 错误或显式 setError）判断是否重试**，并按指数退避重试到 `max_retries`。`<true>` 特化仅用于 async insert + async dedup。
