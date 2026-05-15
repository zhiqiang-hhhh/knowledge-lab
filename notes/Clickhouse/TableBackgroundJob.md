[TOC]

### BackgroundJobExecutor
目前我们可以将 Clickhouse 中的线程池分为两类：一类是每个 table 自己独占的，另一类是所有 table 公用的。BackgroundJobExecutor 会为每个 table 创建一定数量的线程，这些线程与公用线程不在同一个线程池内。

基类是 IBackgroundJobExecutor，其中的重要代码：
```c++
class IBackgroundJobExecutor {
private:
    ...
    std::unordered_map<PoolType, ThreadPool> pools;
    BackgroundSchedulePool::TaskHolder scheduling_task;
    ...
protected:
    IBackgroundJobExecutor(
        ContextPtr global_context_,
        const BackgroundTaskSchedulingSettings & sleep_settings_,
        const std::vector<PoolConfig> & pools_configs_);
    ...
}
```
该基类的构造函数：
```c++
IBackgroundJobExecutor::IBackgroundJobExecutor(
        ContextPtr global_context_,
        const BackgroundTaskSchedulingSettings & sleep_settings_,
        const std::vector<PoolConfig> & pools_configs_)
    : WithContext(global_context_)
    , sleep_settings(sleep_settings_)
    , rng(randomSeed())
{
    for (const auto & pool_config : pools_configs_)
    {
        pools.try_emplace(pool_config.pool_type, pool_config.max_pool_size, 0, pool_config.max_pool_size, false);
        pools_configs.emplace(pool_config.pool_type, pool_config);
    }
}
```
pools 类型是 `std::unordered_map<PoolType, ThreadPool>`，ThreadPool 中的线程都是来自 Global Thread Pool（默认大小 10000）。

再来看 BackgroundJobsExecutor 的构造函数：
```c++
BackgroundJobsExecutor::BackgroundJobsExecutor(
       MergeTreeData & data_,
       ContextPtr global_context_)
    : IBackgroundJobExecutor(
        global_context_,
        global_context_->getBackgroundProcessingTaskSchedulingSettings(),
        {PoolConfig{PoolType::MERGE_MUTATE, global_context_->getSettingsRef().background_pool_size, CurrentMetrics::BackgroundPoolTask},
         PoolConfig{PoolType::FETCH, global_context_->getSettingsRef().background_fetches_pool_size, CurrentMetrics::BackgroundFetchesPoolTask}})
    , data(data_)
{
}
```
BackgroundJobsExecutor 对象构造时创建了两个线程池。一个线程池负责执行 MERGE_MUTATE 任务，另一个负责执行 FETCH 任务。


以StorageMergeTree为例，`createTable`的最后，通过`IStorage::startup()`将 task 塞进线程池的执行队列。
```c++
bool InterpreterCreateQuery::doCreateTable(ASTCreateQuery & create,
                                           const InterpreterCreateQuery::TableProperties & properties)
{
    ...
    StoragePtr res;
    ...
    res->startup();
    return true;
}

void StorageMergeTree::startup()
{
    clearOldPartsFromFilesystem();
    clearOldWriteAheadLogs();
    clearEmptyParts();

    /// Temporary directories contain incomplete results of merges (after forced restart)
    ///  and don't allow to reinitialize them, so delete each of them immediately
    clearOldTemporaryDirectories(0);

    /// NOTE background task will also do the above cleanups periodically.
    time_after_previous_cleanup.restart();
    ...
    // BackgroundJobsExecutor
    background_executor.start();
    startBackgroundMovesIfNeeded();
    ...
}
```
MergeTree 的 `BackgroundJobsExecutor background_executor` 是在`StorageMergeTree`的构造函数里创建的：
```cpp
StorageMergeTree::StorageMergeTree(
    ...
    )
    : ..., background_executor(*this, getContext()) ... {}
``` 
实际 start执行`IBackgroundJobExecutor::start()`
```cpp
void IBackgroundJobExecutor::start()
{
    std::lock_guard lock(scheduling_task_mutex);
    if (!scheduling_task)
    {
        scheduling_task = getContext()->getSchedulePool().createTask(
            getBackgroundTaskName(), [this]{ jobExecutingTask(); });
    }

    scheduling_task->activateAndSchedule();
}
```
`start`之后，函数对象执行的是`IBackgroundJobExecutor`的成员函数`jobExecutingTask`

```cpp
void IBackgroundJobExecutor::jobExecutingTask()
{
    auto job_and_pool = getBackgroundJob();
    ...
    bool job_succeed = job();
    ...
}

std::optional<JobAndPool> BackgroundJobsExecutor::getBackgroundJob()
{
    return data.getDataProcessingJob();
}
```
所以，对于 MergeTree，其创建的后台任务为`MergeTreeData::getDataProcessingJob()`

### 线程执行数量
**非常重要的是，BackgroundJobExecutor 创建 n 个线程，并不表示每个 table 都会有 n 个 backgroundjob 同时执行**。
以 FETCH 任务为例，每个 table 都会包含一个线程池，其中有 background_fetches_pool_size (m) 个线程，那么似乎所有 n 张表加起来应该最多有 n * m 个同时执行的 task（假设不超过物理CPU数量）。但是实际上全局最多只会有 m 个线程执行 fetch。这是因为，在每条 log 执行前，ReplicatedMergeTreeQueue 会检查该 log 是否应该执行，对于 GET_PART任务，其检查逻辑如下：
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

    return true;
}
```
注意这里的 CurrentMetrics 是一个全局的变量，也就是说，**只要全局当时执行 FETCH 的线程数量达到 replicated_fetches_pool_size（等于users.xml 中的 backgroud_fetch_pool_size)，那么本条 GET_PART log就不会执行**

#### CurrentMetrics
```c++
void IBackgroundJobExecutor::jobExecutingTask()
try
{
    auto job_and_pool = getBackgroundJob();
    if (job_and_pool) /// If we have job, then try to assign into background pool
    {
        auto & pool_config = pools_configs[job_and_pool->pool_type];
        auto metric_decrementor = std::make_shared<ParanoidMetricDecrementor>(pool_config.tasks_metric);
        /// If corresponding pool is not full increment metric and assign new job
        if (incrementMetricIfLessThanMax(CurrentMetrics::values[pool_config.tasks_metric], pool_config.max_pool_size))
        {
            ...
        }
    }
    ...
}
```
每个BackgroundJobExecutor在执行自己的job时，会将全局 CurrentMetrics 中对应的指标加一





### 后台任务调度

###

    getDataProcessingJob
        processQueueEntry
            executeLogEntry
                tryExecuteMerge