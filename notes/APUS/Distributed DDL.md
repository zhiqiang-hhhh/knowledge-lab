[TOC]

## Clickhouse
### Clickhouse DDL Overview
```c++
void TCPHandler::runImpl(){
    ...
    while(true){
        ...
        state.io = executeQuery(state.query, query_context, false, state.stage, may_have_embedded_data);
        ...
        else if (state.io.in)
            processOrdinaryQuery();
        ...
        state.io.onFinish();
        ...
        watch.stop();

        LOG_DEBUG(log, "Processed in {} sec.", watch.elapsedSeconds());

        /// It is important to destroy query context here. We do not want it to live arbitrarily longer than the query.
        query_context.reset();
    }
}
```
上述伪代码描述的是一个比较宏观的DDL Query执行过程。
对于普通的DDL，`executeQuery`会完成本地的DDL执行，对于一个Distributed DDL，`executeQuery`只是在Zookeeper上创建必要的`DDLLogEntry`，并没有真正进行DDL动作。

最终所有的query都会执行到函数`executeQueryImpl`
```c++
static std::tuple<ASTPtr, BlockIO> executeQueryImpl(
    const char * begin,
    const char * end,
    ContextPtr context,
    bool internal,
    QueryProcessingStage::Enum stage,
    bool has_query_tail,
    ReadBuffer * istr)
{
    ...
    /// [HZQ] 通过 ast 获取对应的 interpreter
    /// 比如 create table 就会 返回 InterpreterCreateQuery
    auto interpreter = InterpreterFactory::get(ast, context, SelectQueryOptions(stage).setInternal(internal));
    ...
    OpenTelemetrySpanHolder span("IInterpreter::execute()");

    res = interpreter->execute();
    ...
    return std::make_tuple(ast, std::move(res));
}
```
InterpreterFactory::get() 函数根据 ast 创建对应的 interpreter 对象


对于形如`Create table xxx on cluster yyy ...`的语句，`res = interpreter->execute()`会执行到`executeDDLQueryOnCluster`。
### executeDDLQueryOnCluster
精简代码：
```c++
BlockIO executeDDLQueryOnCluster(const ASTPtr & query_ptr, ContextPtr context, AccessRightsElements && query_requires_access){
    ...
    auto * query = dynamic_cast<ASTQueryWithOnCluster *>(query_ptr.get());
    ...
    query->cluster = context->getMacros()->expand(query->cluster);
    ClusterPtr cluster = context->getCluster(query->cluster);
    DDLWorker & ddl_worker = context->getDDLWorker();
    ...
    DDLLogEntry entry;
    entry.hosts = std::move(hosts);
    entry.query = queryToString(query_ptr);
    entry.initiator = ddl_worker.getCommonHostID();
    entry.setSettingsIfRequired(context);
    String node_path = ddl_worker.enqueueQuery(entry);

    return getDistributedDDLStatus(node_path, entry, context);
}
```
`executeDDLQueryOnCluster`在OLAP仓库下的[MR](https://git.woa.com/TencentClickHouse/TencentOLAP/merge_requests/29)中，目前已经替换为将DDL转发到FE。
原始Clickhouse中的逻辑比较直观，用一句话概括：

    Pushes distributed DDL query to the queue.
    Returns DDLQueryStatusInputStream, which reads results of query execution on each host in the cluster.

返回的是一个`DDLQueryStatusInputStream`对象，该对象会被`ProcessOrdinaryQuery`处理。

### ProcessOrdinaryQuery
```c++
void TCPHandler::ProcessOrdinaryQuery(){
    ...
    /// Pull query execution result, if exists, and send it to network.
    if(state.io.in){
        ...
        if(Block header = state.io.in->getHeader()){
            // send schema
            sendDate(header);
        }

        // 创建异步读流，用来从BlockStream中拉取数据
        AsynchronousBlockInputStream async_in(state.io.in);
        async_in.readPrefix();
        while (true)
        {
            if (isQueryCancelled())
            {
                async_in.cancel(false);
                break;
            }

            if (after_send_progress.elapsed() / 1000 >= query_context->getSettingsRef().interactive_delay)
            {
                /// Some time passed.
                after_send_progress.restart();
                sendProgress();
            }

            sendLogs();

            if (async_in.poll(query_context->getSettingsRef().interactive_delay / 1000))
            {
                const auto block = async_in.read();
                if (!block)
                    break;

                if (!state.io.null_format)
                    sendData(block);
            }
        }
        async_in.readSuffix();

        
    }
}
```
在`const auto block = async_in.read();`处会调用到`Block DDLQueryStatusInputStream::readImpl()`

### DDLQueryStatusInputStream 
```c++
class DDLQueryStatusInputStream final : public IBlockInputStream{
public:
    ...
    Block readImpl() override;

private:
    ...
    String node_path;
    ContextPtr context;
    Stopwatch watch;
    Poco::Logger * log;

    Block sample;

    NameSet waiting_hosts;
    NameSet finished_hosts;
    NameSet ignoring_hosts;
    String cueernt_active_hosts;
    size_t num_hosts_finished;

    Int64 timeout_seconds = 120;
    
}
```
`waiting_hosts`下记录了本次DDL的所有目标replicas。
```c++
sample = Block{
    {std::make_shared<DataTypeString>(),                         "host"},
    {std::make_shared<DataTypeUInt16>(),                         "port"},
    {maybe_make_nullable(std::make_shared<DataTypeInt64>()),     "status"},
    {maybe_make_nullable(std::make_shared<DataTypeString>()),    "error"},
    {std::make_shared<DataTypeUInt64>(),                         "num_hosts_remaining"},
    {std::make_shared<DataTypeUInt64>(),                         "num_hosts_active"},
};
```
`DDLQueryStatusInputStream`本身被当作是来自“某张表”的数据流，`sample`相当于定义了这张表的`schema`，而具体这张表则是一张内存中的表，在`readImpl`中被创建、修改。

关键的`readImpl`实现：
```c++
Block DDLQueryStatusInputStream::readImpl(){
    // 如果所有的host全部完成了DDL，或者 time_exceeded
    // return 空 或者 throw exception
    while (res.rows() == 0)
    {
        if (isCancelled())
        {
            bool throw_if_error_on_host = context->getSettingsRef().distributed_ddl_output_mode != DistributedDDLOutputMode::NEVER_THROW;
            if (first_exception && throw_if_error_on_host)
                throw Exception(*first_exception);

            return res;
        }

        if (timeout_seconds >= 0 && watch.elapsedSeconds() > timeout_seconds)
        {
            size_t num_unfinished_hosts = waiting_hosts.size() - num_hosts_finished;
            size_t num_active_hosts = current_active_hosts.size();

            constexpr const char * msg_format = "Watching task {} is executing longer than distributed_ddl_task_timeout (={}) seconds. "
                                                "There are {} unfinished hosts ({} of them are currently active), "
                                                "they are going to execute the query in background";
            if (throw_on_timeout)
                throw Exception(ErrorCodes::TIMEOUT_EXCEEDED, msg_format,
                                node_path, timeout_seconds, num_unfinished_hosts, num_active_hosts);

            timeout_exceeded = true;
            LOG_INFO(log, msg_format, node_path, timeout_seconds, num_unfinished_hosts, num_active_hosts);

            NameSet unfinished_hosts = waiting_hosts;
            for (const auto & host_id : finished_hosts)
                unfinished_hosts.erase(host_id);

            /// Query is not finished on the rest hosts, so fill the corresponding rows with NULLs.
            MutableColumns columns = sample.cloneEmptyColumns();
            for (const String & host_id : unfinished_hosts)
            {
                auto [host, port] = parseHostAndPort(host_id);
                size_t num = 0;
                columns[num++]->insert(host);
                if (by_hostname)
                    columns[num++]->insert(port);
                columns[num++]->insert(Field{});
                columns[num++]->insert(Field{});
                columns[num++]->insert(num_unfinished_hosts);
                columns[num++]->insert(num_active_hosts);
            }
            res = sample.cloneWithColumns(std::move(columns));
            return res;
        }

        if (num_hosts_finished != 0 || try_number != 0)
        {
            sleepForMilliseconds(std::min<size_t>(1000, 50 * (try_number + 1)));
        }

        if (!zookeeper->exists(node_path))
        {
            throw Exception(ErrorCodes::UNFINISHED,
                            "Cannot provide query execution status. The query's node {} has been deleted by the cleaner since it was finished (or its lifetime is expired)",
                            node_path);
        }

        Strings new_hosts = getNewAndUpdate(getChildrenAllowNoNode(zookeeper, fs::path(node_path) / "finished"));
        ++try_number;
        if (new_hosts.empty())
            continue;

        current_active_hosts = getChildrenAllowNoNode(zookeeper, fs::path(node_path) / "active");

        MutableColumns columns = sample.cloneEmptyColumns();
        for (const String & host_id : new_hosts)
        {
            ExecutionStatus status(-1, "Cannot obtain error message");
            {
                String status_data;
                if (zookeeper->tryGet(fs::path(node_path) / "finished" / host_id, status_data))
                    status.tryDeserializeText(status_data);
            }

            auto [host, port] = parseHostAndPort(host_id);

            if (status.code != 0 && first_exception == nullptr)
                first_exception = std::make_unique<Exception>(status.code, "There was an error on [{}:{}]: {}", host, port, status.message);

            ++num_hosts_finished;

            size_t num = 0;
            columns[num++]->insert(host);
            if (by_hostname)
                columns[num++]->insert(port);
            columns[num++]->insert(status.code);
            columns[num++]->insert(status.message);
            columns[num++]->insert(waiting_hosts.size() - num_hosts_finished);
            columns[num++]->insert(current_active_hosts.size());
        }
        res = sample.cloneWithColumns(std::move(columns));
    }
}
```
`columns`就是提到的内存表。其内容则是根据Zookeeper中node的内容计算出来的结果。


## FE DDL 并发
FE上一个DDL的完整执行周期内，最少涉及到3个线程的参与：

1. submit job

```java
public CHDDLJob submitDDLJob(TExecCHDDLReq request) {
    long backendId = request.getHeader().getBackendId();
    String tenantName = systemInfoService.getBackend(backendId).getOwnerClusterName();
    CHTenant tenant = nameToTenant.get(tenantName);

    tenant.WriteLock();
    CHDDLJob job = null;

    try {
        ...
        job = new CHDDLJob(...);
    } final {
        tenant.WriteUnLock();
    }

    jobHandler.submitJob(job)
    return job;
}
```
创建 job 以及 init job 期间，整个 tenant 被加了写锁，tenant 包含的字段如下：
```plantuml
class CHTenant {
    - tenantName : String
    - tenantId : long
    - idToCHCluster : Map<Long, CHCluster>
    - nameToCHCluster : Map<String, CHCluster>
    - idToDb : Map<String, CHDatabase>
    - nameToDb : Map<String, CHDatabase>
    - tabletInvertIndex : CHTabletInvertIndex
}

CHTenant *-- CHTabletInvertIndex

class CHTabletInvertIndex {
    + uidToTablet : Map<String, CHTablet>
    + addTablet(CHTablet) : void
    + getTablet(String tabletId) : CHTablet
}

CHTenant *-- CHCluster

class CHCluster{
    - tenantId : long
    - clusterId : long
    - clusterName : String
    - shards : Map<Integer, CHShard>
}

CHTenant *-- CHDatabase

class CHDatabase {
    - databaseUid : String
    - databaseName : String
    - idToTable : Map<String, CHTable>
    - nameToTable : Map<String, CHTable>
}
```
submit job 期间，CHDDLJobHandler 加写锁，保护 CHDDLJobHandler 的 runningJobs 以及 finishedJobs 字段

2. CHDDLJobHandler::runAfterCatalogReady
 
```java
protected void runAfterCatalogReady() {
    WriteLock();
    for (job : runningJobs) {
        CHTenant chTenant = Catalog.getCurrentCatalog().getTenantMgr().getTenant(chddlJob.getTenantId());
        chTenant.WriteLock();
        chTenant.executeTask(
            ...
            job.run();
            ...
            job.cancelJob() // If necessary
        )
        chTenant.WriteUnLock();
    }
    WriteUnLock();
}
```

runAfterCatalogReady 执行期间 lock 有重叠的情况：先对 CHDDLJobHandler 加写锁，然后再对 tenant 加写锁

3. finish task

```java
public TMasterResult finishTask(TFinishTaskRequest request){
    ...
    AgentTask task = AgentTaskQueue.getTask(backendId, taskType, signature);
    ...
    finishCHDDLTask(task, request)
    ...
}
```
finish task 阶段只涉及到 task 对象的访问。此阶段可能会与执行 CHDDLJobHandler::runAfterCatalogReady() 函数的线程有竞争。