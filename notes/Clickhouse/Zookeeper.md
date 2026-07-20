# Zookeeper
```cpp
void ZooKeeper::pushRequest(RequestInfo && info) 
{
    ...
    info.time = clock::now(); 

    {
        // 这段逻辑有点意思，zk client 自己维护了一个xid？
        if (!info.request->xid)
        {
            info.request->xid = next_xid.fetch_add(1);
            if (!use_xid_64)
                info.request->xid = static_cast<int32_t>(info.request->xid);

            if (info.request->xid == close_xid)
                throw Exception::fromMessage(Error::ZSESSIONEXPIRED, "xid equal to close_xid");
            if (info.request->xid < 0)
                throw Exception::fromMessage(Error::ZSESSIONEXPIRED, "XID overflow");

            if (auto * multi_request = dynamic_cast<ZooKeeperMultiRequest *>(info.request.get()))
            {
                for (auto & request : multi_request->requests)
                    dynamic_cast<ZooKeeperRequest &>(*request).xid = multi_request->xid;
            }
        }

        if (!requests_queue.tryPush(std::move(info), args.operation_timeout_ms))
        {
            if (requests_queue.isFinished())
                throw Exception::fromMessage(Error::ZSESSIONEXPIRED, "Session expired");

            throw Exception(Error::ZOPERATIONTIMEOUT, "Cannot push request to queue within operation timeout of {} ms", args.operation_timeout_ms);
        }
    }

    ProfileEvents::increment(ProfileEvents::ZooKeeperTransactions);
}
```

```cpp
void ZooKeeper::sendThread()
{
    auto prev_heartbeat_time = clock::now();

    while (!requests_queue.isFinished())
    {
        auto prev_bytes_sent = out->count();

        auto now = clock::now();
        auto next_heartbeat_time = prev_heartbeat_time + std::chrono::milliseconds(args.session_timeout_ms / 3);

        if (next_heartbeat_time > now)
        {
            /// Wait for the next request in queue. No more than operation timeout. No more than until next heartbeat time.
            UInt64 max_wait = std::min(
                static_cast<UInt64>(std::chrono::duration_cast<std::chrono::milliseconds>(next_heartbeat_time - now).count()),
                static_cast<UInt64>(args.operation_timeout_ms));

            // 等到下一个 request 或者 heartbeat 的时间
            RequestInfo info;
            if (requests_queue.tryPop(info, max_wait))
            {
                ...
                if (info.request->xid != close_xid)
                {
                    CurrentMetrics::add(CurrentMetrics::ZooKeeperRequest);
                    std::lock_guard lock(operations_mutex);
                    operations[info.request->xid] = info;
                }
            }
        }
        else
        {
            /// Send heartbeat.
            prev_heartbeat_time = clock::now();

            ZooKeeperHeartbeatRequest request;
            request.xid = PING_XID;
            request.write(getWriteBuffer(), use_xid_64);
            flushWriteBuffer();
        }

        ProfileEvents::increment(ProfileEvents::ZooKeeperBytesSent, out->count() - prev_bytes_sent);
    }
}
```
### 重试

```cpp

```

```cpp
class ZooKeeperRetriesControl
{
public:
    void retryLoop(auto && f, auto && iteration_cleanup) {
        while (current_iteration == 0 || canTry()) {
            iteration_succeeded = true;       // 每次迭代开头乐观地假设成功
            try {
                f();                          // 跑用户的 lambda
                iteration_cleanup();
            }
            catch (const KeeperException & e) {
                iteration_cleanup();
                if (!isHardwareError(e.code)) throw;   // 非硬件错误 → 直接抛出,不重试
                setKeeperError(...);          // 硬件错误 → iteration_succeeded=false, total_failures++
            }
            catch (...) {
                iteration_cleanup();
                throw;                        // 其他任何异常 → 抛出,不重试
            }
            current_iteration++;
        }
    }
}
```
