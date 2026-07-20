# Query Execution Notes

## 1. TCPHandler 入口

```cpp
void TCPHandler::runImpl() {
    ...
    /// Processing Query
    // Build plan + build pipeline
    std::tie(query_state->parsed_query, query_state->io)
        = executeQuery(query_state->query, query_state->query_context, QueryFlags{}, query_state->stage);
    ...
    // pulling 表示从 DB 拉取结果（如 SELECT）
    else if (query_state->io.pipeline.pulling())
    {
        processOrdinaryQuery(query_state.value());
        query_state->io.onFinish();
    }
}
```

## 2. Plan 阶段

```cpp
static BlockIO executeQueryImpl(
    const char * begin,
    const char * end,
    ContextMutablePtr context,
    QueryFlags flags,
    QueryProcessingStage::Enum stage,
    ReadBuffer * istr,
    ASTPtr & out_ast)
{
    ...
    // Build plan tree
    if (auto * interpreter_with_analyzer = dynamic_cast<InterpreterSelectQueryAnalyzer *>(interpreter.get()))
        interpreter_with_analyzer->getQueryPlan();
    ...
    // Build pipeline
    res = interpreter->execute();
}
```

对于分布式表，是否引入 `ReadFromRemote` 在 build plan tree 阶段决定。

```cpp
void Planner::buildPlanForQueryNode() {
    ...
    JoinTreeQueryPlan join_tree_query_plan;
    if (planner_context->getMutableQueryContext()->canUseTaskBasedParallelReplicas()
        && planner_context->getGlobalPlannerContext()->parallel_replicas_node == &query_node)
    {
        join_tree_query_plan = buildQueryPlanForParallelReplicas(
            query_node,
            planner_context,
            select_query_info.storage_limits);
    }
    else
    {
        auto top_level_identifiers = collectTopLevelColumnIdentifiers(query_tree, planner_context);
        join_tree_query_plan = buildJoinTreeQueryPlan(
            query_tree,
            select_query_info,
            select_query_options,
            top_level_identifiers,
            planner_context);
    }
    ...
}

ClusterProxy::executeQuery(...) {
    ...
    SelectStreamFactory::Shards remote_shards;
    ...
    stream_factory.createForShard(
        shard_info,
        query_for_shard,
        main_table,
        table_func_ptr,
        new_context,
        plans,
        remote_shards,
        static_cast<UInt32>(shards),
        parallel_replicas_enabled,
        shard_filter_generator);
    ...
    if (!remote_shards.empty()) {
        ...
        auto read_from_remote = std::make_unique<ReadFromRemote>(
            std::move(remote_shards),
            header,
            processed_stage,
            main_table,
            table_func_ptr,
            new_context,
            getThrottler(context),
            std::move(scalars),
            std::move(external_tables),
            log,
            shards,
            query_info.storage_limits,
            not_optimized_cluster->getName());

        read_from_remote->setStepDescription("Read from remote replica");
        plan->addStep(std::move(read_from_remote));
        plan->addInterpreterContext(new_context);
        plans.emplace_back(std::move(plan));
    }
}
```

`SelectStreamFactory::createForShard` 决定副本选择策略。

## 3. Initialize Pipeline 阶段
这一阶段里，PlanStep 将会创建一组 processor，同名 processor 会有多个实例，表示并行处理 block，同一个 plan step 下可能会创建多个 processor，表示对于 block 有多阶段的操作。

### ReadFromMergeTree::initializePipeline

#### getAnalysisResult
索引分析阶段，主键索引以及skipping index就是在这个阶段 apply 的。
#### spreadMarkRanges
根据索引分析之后的 parts_with_ranges，和最大并行度要求，来决定实际 ReadFromMergeTree 的并行度。
```cpp
spreadMarkRanges
    ReadFromMergeTree::read
        ReadFromMergeTree::readFromPool
            MergeTreeReadPool(...)
                fillPerThreadInfo(...)

            Pipes pipes;
    for (size_t i = 0; i < pool_settings.threads; ++i)
    {
        auto algorithm = std::make_unique<MergeTreeThreadSelectAlgorithm>(i);

        auto processor
            = std::make_unique<MergeTreeSelectProcessor>(pool, std::move(algorithm), prewhere_info, actions_settings, reader_settings);

        auto source = std::make_shared<MergeTreeSource>(std::move(processor), data.getLogName());

        if (i == 0)
            source->addTotalRowsApprox(total_rows);

        pipes.emplace_back(std::move(source));
    }
    return pipes    
```

同一个 MergeTreeReadPool 被多个 MergeTreeSelectProcessor 共享，每个 processor 用自己的 thread_idx 去调用：`pool.getTask(thread_idx, previous_task)`
#### backoff
ReadFromMergeTree有两个backoff机制来动态控制并发：
1. 如果 IO 侧延迟过大，那么会降低 ReadFromMergeTreeTask 的并发数量
2. 如果是下游消费过慢，那么 pipeline 调度会自动实现 ReadFromMergeTree 并发降低

```
下游消费慢
    -> 下游 input/output port 状态变化
    -> 上游 source 的 output port 不能 push
    -> ISource::prepare() 返回 PortFull
    -> Executor 不会调用这个 source 的 work()
    -> source 不会进入 MergeTreeSelectProcessor::read()
    -> 不会继续 pool.getTask()
```


## 4. Execute 阶段

```cpp
void TCPHandler::processOrdinaryQuery(QueryState & state) {
    ...
    PullingAsyncPipelineExecutor executor(pipeline);
    Block block;
    while (executor.pull(block, interactive_delay / 1000))
    {
        ...
    }
}

bool PullingAsyncPipelineExecutor::pull(Chunk & chunk, uint64_t milliseconds)
{
    if (!data)
    {
        data = std::make_unique<Data>();
        data->executor = std::make_shared<PipelineExecutor>(pipeline.processors, pipeline.process_list_element);
        data->executor->setReadProgressCallback(pipeline.getReadProgressCallback());
        data->lazy_format = lazy_format.get();

        auto func = [&, thread_group = CurrentThread::getGroup()]()
        {
            threadFunction(*data, thread_group, pipeline.getNumThreads(), pipeline.getConcurrencyControl());
        };

        data->thread = ThreadFromGlobalPool(std::move(func));
    }

    bool is_execution_finished
        = !data->executor->checkTimeLimitSoft() || (lazy_format ? lazy_format->isFinished() : data->is_finished.load());

    if (is_execution_finished)
    {
        /// If lazy format is finished, we don't cancel pipeline but wait for main thread to be finished.
        data->is_finished = true;
        /// Wait thread and rethrow exception if any.
        cancel();
    }

    // Key point
    chunk = lazy_format->getChunk(milliseconds);
    ...
    return true;
}

static void threadFunction(
    PullingAsyncPipelineExecutor::Data & data,
    ThreadGroupPtr thread_group,
    size_t num_threads,
    bool concurrency_control)
{
    try
    {
        ThreadGroupSwitcher switcher(thread_group, "QueryPullPipeEx");
        data.executor->execute(num_threads, concurrency_control);
    }
    catch (...)
    {
        data.exception = std::current_exception();
        data.has_exception = true;

        /// Finish lazy format in case of exception. Otherwise thread.join() may hang.
        data.lazy_format->finalize();
    }

    data.is_finished = true;
}
```

关键点：

- 第一次执行时 `!data == true`，通过 `ThreadFromGlobalPool` 提交后台任务。
- 后台线程核心执行 `data.executor->execute(num_threads, concurrency_control);`。
- 前台 `while (executor.pull(...))` 循环的核心是 `chunk = lazy_format->getChunk(milliseconds);`。
- `lazy_format` 可看作一个 chunk queue：
  - 入口：`Executor::execute` 生产数据。
  - 出口：`TCPHandler` 线程消费数据。

```cpp
void PipelineExecutor::execute(size_t num_threads, bool concurrency_control) {

}
```

## 4. ReadFromMergeTree 说明

`ReadFromMergeTree` 不是运行时真正读数据的 processor，而是 QueryPlan 里的一个 source step。它的职责是把 MergeTree 的读路径展开成可执行 pipeline。

可以理解为：

```text
QueryPlan:
  ReadFromMergeTree

Pipeline:
  MergeTreeSelect(...)
  MergeTreeSelect(...)
  MergeTreeSelect(...)
  ...
```

也就是说，不是创建多个 `ReadFromMergeTree` 实例，而是一个 `ReadFromMergeTree` step 在 `initializePipeline()` 阶段创建多个真正执行读取的 source processors。

这些 source processors 底层是 `MergeTreeSource`，但 `EXPLAIN PIPELINE` 里通常显示为：

```text
MergeTreeSelect(pool: ..., algorithm: ...)
MergeTreeSelect(pool: ..., algorithm: ...)
MergeTreeSelect(pool: ..., algorithm: ...)
```

原因是：

```cpp
MergeTreeSource::getName()
{
    return processor->getName();
}
```

所以你看到的是 `MergeTreeSelectProcessor` 的名字。

为什么会有多个 `MergeTreeSelect`：

- MergeTree 读取天然可并行拆分（按 part / mark ranges）。
- `ReadFromMergeTree` 会先根据 partition key、primary key、skip index 选择 parts / mark ranges。
- 再结合 `max_threads`、`max_streams_for_merge_tree_reading`、数据量、本地/远端存储等因素创建多个 stream。

大致结构：

```text
ReadFromMergeTree
  -> select parts / mark ranges
  -> create MergeTreeReadPool
  -> create N MergeTreeSelectProcessor
  -> wrap each with MergeTreeSource
  -> run sources in parallel
```

多个 `MergeTreeSelect` 通常共享一个 `MergeTreeReadPool`，动态领取 `MergeTreeReadTask`，可并行处理：

- IO 读取
- 压缩块读取与解压
- 列反序列化
- PREWHERE 过滤
- 剩余列读取

这种动态任务池可以减少拖尾：某个 part 特别大或某个远端读取慢时，其他 source 读完后仍可继续领取新任务。

除了 `MergeTreeSelect`，展开 pipeline 时还可能出现：

- `NullSource`：没有可读 range。
- `FilterTransform`：sampling 或额外过滤。
- `ExpressionTransform`：sorting key 表达式、projection、临时列裁剪、header conversion。
- `ConcatProcessor`：某些场景下串行拼接以保持顺序。
- `ReverseTransform`：反向有序读取。

若查询带 `FINAL`，还会按引擎追加 sorted merge processor，例如 ReplacingMergeTree 的 `ReplacingSorted`。

整体可以总结为：

```text
One ReadFromMergeTree plan step
  -> multiple MergeTreeSelect source processors
  -> optional Filter / Expression / Concat / Reverse
  -> optional FINAL processors (ReplacingSorted / CollapsingSorted / SummingSorted ...)
```

结论：不是“创建多个 `ReadFromMergeTree` processor”，而是“一个 `ReadFromMergeTree` plan step 展开成多个执行读取的 `MergeTreeSelect` source processors，并按查询需求接后续 transforms”。



```
avg-cpu:  %user   %nice %system %iowait  %steal   %idle
           5.63    0.00    3.32   89.92    0.00    1.13

Device            r/s     rMB/s   rrqm/s  %rrqm r_await rareq-sz     w/s     wMB/s   wrqm/s  %wrqm w_await wareq-sz     d/s     dMB/s   drqm/s  %drqm d_await dareq-sz     f/s f_await  aqu-sz  %util
loop0            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop1            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop10           0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop11           0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop12           0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop13           0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop14           0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop2            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop3            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop4            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop5            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop6            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop7            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop8            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
loop9            0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00    0.00   0.00
nvme0n1       6237.50     29.62  1318.50  17.45    8.82     4.86 1843.50     16.59  2065.50  52.84    3.09     9.22    0.00      0.00     0.00   0.00    0.00     0.00    0.00    0.00   60.71 100.00 
```