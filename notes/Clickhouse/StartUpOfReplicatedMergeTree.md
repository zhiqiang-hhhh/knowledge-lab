```cpp
StorageReplicatedMergeTree::startupImpl(bool from_attach_thread, const ZooKeeperRetriesInfo & zookeeper_retries_info) {
    if (!has_metadata_in_zookeeper.has_value() || !*has_metadata_in_zookeeper)
    {
        if (!std::exchange(is_readonly_metric_set, true))
            CurrentMetrics::add(CurrentMetrics::ReadonlyReplica);

        LOG_TRACE(log, "No connection to ZooKeeper or no metadata in ZooKeeper, will not startup");
        return;     
    } 

    // 如果有 zk
    try
    {
        auto zookeeper = getZooKeeper();
        // 注册用来 exchange part 的 http endpoint
        InterserverIOEndpointPtr data_parts_exchange_ptr = std::make_shared<DataPartsExchange::Service>(*this);
        getContext()->getInterserverIOHandler().addEndpoint(
            data_parts_exchange_ptr->getId(getEndpointName()), data_parts_exchange_ptr);

        // 实际上没有作用，只是为了保持兼容
        startBeingLeader(zookeeper_retries_info);

        if (from_attach_thread)
        {
            ...
        }
        else
        {
            restarting_thread.start(/*schedule=*/true);
            // schedule 超过 10秒失败的话，会打一行日志
            while (!startup_event.tryWait(10 * 1000))
                LOG_TRACE(log, "Waiting for RestartingThread to startup table");
        }

        // schedule 成功

        // 如果 start 期间又被 shutdown，那么就终止，抛异常
        auto lock = std::unique_lock<std::mutex>(flush_and_shutdown_mutex, std::defer_lock);
        do
        {
            if (shutdown_prepared_called.load() || shutdown_called.load())
                throw Exception(ErrorCodes::TABLE_IS_DROPPED, "Cannot startup table because it is dropped");
        }
        while (!lock.try_lock());

        // session_expired_callback
        // 针对 ZK SessionExipred 事件，注册重启事件
        // 并且在当前对象里保存事件callback的handler，当当前对象shutdown的时候，撤销 subscribe
        session_expired_callback_handler = EventNotifier::instance().subscribe(Coordination::Error::ZSESSIONEXPIRED, [this]()
        {
            LOG_TEST(log, "Received event for expired session. Waking up restarting thread");
            restarting_thread.start(true);
        });

        // 如果当前 table 有需要做 background move，那么就创建一个相关的task
        startBackgroundMovesIfNeeded();
    }
    catch (...)
    {
        // startup 期间有任何异常，那么需要stop所有startup期间创建的任务。
        if (from_attach_thread)
        {
            restarting_thread.shutdown(/* part_of_full_shutdown */false);
            ...
        }
        else
        {
            shutdown(false);
        }
    }
}

void StorageReplicatedMergeTree::shutdown(bool)
{
    if (shutdown_called.exchange(true))
        return;

    flushAndPrepareForShutdown();

    // shutdown 之前等待一会儿，这样unique part可以被其他replica fetch
    try
    {
        waitForUniquePartsToBeFetchedByOtherReplicas(*shutdown_deadline);
    }
    catch (const Exception & ex)
    {
        if (ex.code() == ErrorCodes::LOGICAL_ERROR)
            throw;

        tryLogCurrentException(log, __PRETTY_FUNCTION__);
    }
}
```

```cpp

void ReplicatedMergeTreeRestartingThread::shutdown(bool part_of_full_shutdown)
{
    /// Stop restarting_thread before stopping other tasks - so that it won't restart them again.
    need_stop = part_of_full_shutdown;
    task->deactivate();

    /// Explicitly set the event, because the restarting thread will not set it again
    if (part_of_full_shutdown)
        storage.startup_event.set();

    LOG_TRACE(log, "Restarting thread finished");

    setReadonly(part_of_full_shutdown);

}

void ReplicatedMergeTreeRestartingThread::setReadonly(bool on_shutdown)
{
    bool old_val = false;
    bool became_readonly = storage.is_readonly.compare_exchange_strong(old_val, true);

    if (became_readonly)
    {
        const UInt32 now = static_cast<UInt32>(
            std::chrono::system_clock::to_time_t(std::chrono::system_clock::now()));
        storage.readonly_start_time.store(now, std::memory_order_relaxed);
    }

    /// Do not increment the metric if replica became readonly due to shutdown.
    if (became_readonly && on_shutdown)
        return;

    if (became_readonly)
    {
        chassert(!storage.is_readonly_metric_set);
        storage.is_readonly_metric_set = true;
        CurrentMetrics::add(CurrentMetrics::ReadonlyReplica);
        return;
    }

    /// Replica was already readonly, but we should decrement the metric if it was set because we are detaching/dropping table.
    /// the task should be deactivated if it's full shutdown so no race is present
    if (on_shutdown && std::exchange(storage.is_readonly_metric_set, false))
    {
        CurrentMetrics::sub(CurrentMetrics::ReadonlyReplica);
        chassert(CurrentMetrics::get(CurrentMetrics::ReadonlyReplica) >= 0);
    }
}
```
