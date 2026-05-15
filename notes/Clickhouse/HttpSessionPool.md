# HTTPSessionPool
```
class HTTPSessionPool
{
    std::unordered_map<Key, PoolPtr, Hasher> endpoint_pool;
}
```

```c++
Entry HTTPSessionPool::getSession(
    const Poco::URI & uri,
    const Poco::URI & proxy_uri,
    const ConnectionTimeouts & timeouts,
    size_t max_connection_per_endpoint,
    bool resolve_host = true)
{
    ...
    HTTPSessionPool::Key key{host, port, https, proxy_host, proxy_port, proxy_https};
    auto pool_ptr = endpoints_pool.find(key);
    if (pool_ptr == endpoints_pool.end())
        std::tie(pool_ptr, std::ignore) = endpoints_pool.emplace(
                    key, std::make_shared<SingleEndpointHTTPSessionPool>(host, port, https, proxy_host, proxy_port, proxy_https, max_connections_per_endpoint, resolve_host));
    
    auto retry_timeout = timeouts.connection_timeout.totalMicroseconds();
    auto session = pool_ptr->second->get(retry_timeout);

    ...
}

template <typename TObject>
class PoolBase : private boost::noncopyable
{
public:
    using Object = TObject;
    using ObjectPtr = std::shared_ptr<Object>;
    using Ptr = std::shared_ptr<PoolBase<TObject>>;

private:

    /** The object with the flag, whether it is currently used. */
    struct PooledObject
    {
        PooledObject(ObjectPtr object_, PoolBase & pool_)
            : object(object_), pool(pool_)
        {
        }

        ObjectPtr object;
        bool in_use = false;
        std::atomic<bool> is_expired = false;
        PoolBase & pool;
    };

    using Objects = std::vector<std::shared_ptr<PooledObject>>;

    struct PoolEntryHelper
    {
        explicit PoolEntryHelper(PooledObject & data_) : data(data_), { data.in_use = true; }
        ~PoolEntryHelper()
        {
            std::unique_lock lock(data.pool.mutex);
            data.in_use = false;
            data.pool.available.notify_one();
        }

        PooledObject & data;
    };

    /** The maximum size of the pool. */
    unsigned max_items;

    /** Pool. */
    Objects items;

    /** Lock to access the pool. */
    std::mutex mutex;
    std::condition_variable available;

public:
    
    ...

    Entry get(Poco::Timespan::TiemDiff timeout)
    {
        std::unique_lock lock(mutex);

        while (true)
        {
            for (auto & item : items)
            {
                if (!item->in_use)
                {
                    if (likely(!item->is_expired))
                    {
                        return Entry(*item);
                    }
                    else
                    {
                        expireObject(item->object);
                        item->object = allocObject();
                        item->is_expired = false;
                        return Entry(*item);
                    }
                }
            }

            if (items.size() < max_items)
            {
                ObjectPtr object = allocObject();
                items.emplace_back(std::make_shared<PooledObject>(object, *this));
                return Entry(*item.back());
            }

            if (timeout < 0)
                available.wait(lock);
            else
                available.wait_for(lock, std::chrono::microseconds(timeout));
        }
    }

    ...


}
```