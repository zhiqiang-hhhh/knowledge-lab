```cpp
template<bool async_insert>
void ReplicatedMergeTreeSinkImpl<async_insert>::consume(Chunk & chunk) {
    ...
    ZooKeeperWithFaultInjectionPtr zookeeper = ZooKeeperWithFaultInjection::createInstance(
        settings[Setting::insert_keeper_fault_injection_probability],
        settings[Setting::insert_keeper_fault_injection_seed],
        storage.getZooKeeper(),
        "ReplicatedMergeTreeSink::consume",
        log);
    ...
}
```
返回`ZooKeeperWithFaultInjection`对象。
```cpp
ZooKeeperWithFaultInjection
```