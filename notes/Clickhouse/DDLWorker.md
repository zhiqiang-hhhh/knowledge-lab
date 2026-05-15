Server 启动时创建全局的 DDLWorker 对象
```c++
// Server.cpp
DB::Server::main() {
    ...
    if (has_zookeeper && config.has("distributed_ddl"))
    {
        String ddl_zookeeper_path = config().getString("distributed_ddl.path", "/clickhouse/task_queue/ddl/");
        ...
        global_context->setDDLWorker(std::make_unique<DDLWorker>(
            pool_size,
            ddl_zookeeper_path,
            global_context, 
            &config(), 
            ...
            );
    }
}


void DDLWorker::startup()
{
    main_thread = ThreadFromGlobalPool(&DDLWorker::runMainThread, this);
    cleanup_thread = ThreadFromGlobalPool(&DDLWorker::runCleanupThread, this);
}
```
MainThread 监听 ddl_zookeeper_path，分发任务，最终通过 DDLWorker::processTask 函数执行 DDL Task

中间的处理逻辑很复杂
```c++
void DDLWorker::processTask(DDLTaskBase & task, const ZooKeeperPtr & zookeeper) {
    /// Step 1: Create ephemeral node in active/ status dir.
    /// It allows other hosts to understand that task is currently executing (useful for system.distributed_ddl_queue)
    /// and protects from concurrent deletion or the task.
    ...

    /// Step 2: Execute query from the task.
    ... 
    storage = DatabaseCatalog::instance().tryGetTable(table_id, context);
    ...
    if (task.execute_on_leader)
            {
                tryExecuteQueryOnLeaderReplica(task, storage, rewritten_query, task.entry_path, zookeeper);
            }
            else
            {
                storage.reset();
                tryExecuteQuery(rewritten_query, task, zookeeper);
            }

    /// Step 3: Create node in finished/ status dir and write execution status.
    /// FIXME: if server fails right here, the task will be executed twice. We need WAL here.
    /// NOTE: If ZooKeeper connection is lost here, we will try again to write query status.
    /// NOTE: If both table and database are replicated, task is executed in single ZK transaction.
    ...
}
```

DDLQuery 的最终执行调用的是 DB::executeQuery


    
        
                                                                     