# Doris Heartbeats
心跳管理是Doris实现集群管理的基础。相关的 Thrift 定义在 HearbeatService.thrift
```thrift
...
struct TMasterInfo {
    1: required Types.TNetworkAddress network_address
    2: required Types.TClusterId cluster_id
    3: required Types.TEpoch epoch
    4: optional string token 
    5: optional string backend_ip
    6: optional Types.TPort http_port
    7: optional i64 heartbeat_flags
    8: optional i64 backend_id
}

struct TBackendInfo {
    1: required Types.TPort be_port
    2: required Types.TPort http_port
    3: optional Types.TPort be_rpc_port
    4: optional Types.TPort brpc_port
    5: optional Types.TPort ch_tcp_port
    6: optional Types.TPort ch_http_port
    7: optional string version
    8: optional i64 be_start_time
}

struct THeartbeatResult {
    1: required Status.TStatus status 
    2: required TBackendInfo backend_info
}

service HeartbeatService {
    THeartbeatResult heartbeat(1:TMasterInfo master_info);
}
```

```thrift
struct TFrontendPingFrontendResult {
    1: required TFrontendPingFrontendStatusCode status
    2: required string msg
    3: required i32 queryPort
    4: required i32 rpcPort
    5: required i64 replayedJournalId
    6: required string version
}

struct TFrontendPingFrontendRequest {
   1: required i32 clusterId
   2: required string token
}

service FrontendService{
    ...
    TFrontendPingFrontendResult ping(1: TFrontendPingFrontendRequest request)
    ...
}
```
同时FE在自己的Service中还提供了ping方法。明显该方法用于FE之间的心跳探测。

## Heartbeat Service
添加 backend 到某个 cluster：`alter cluster test_cluster add backends 'xxx:ppp' to shard 1;`，最终执行到 TenantMgr.java 的 addBackends 函数
```java
public void addBackends(String tenantName, String clusterName, List<Pair<String, Integer>> hosts, int shardId) throws UserException {
    // add backends to system info service to track heartbeat and report version info
    systemInfoService.addBackends(hosts, true, tenantName);
    CHTenant chTenant = nameToTenant.get(tenantName);
    ...
    CHCluster chCluster = chTenant.getCluster(clusterName);
    ...
    for (int i = 0; i < hosts.size(); ++i) {
        Backend backend = systemInfoService.getBackendByHostPort(tenantName, hosts.get(i));
        if (backend == null) {
            throw new UserException("Could not find backend " + hosts.get(i));
        }
        chCluster.addBackendToShard(shardId, backend.getId());
        editLog.logAddCHBackend(new BackendOpLog(tenantName, clusterName, backend.getId(), shardId));
    }
}
```
该函数完成两件事：
1. 在内存中完成 addBackends，修改数据结构
2. 在 log 中添加 backend，完成 backend 相关信息的持久化

SystemInfoService 
```java
public void addBackends(List<Pair<String, Integer>> hostPortPairs,
                            boolean isFree, String destCluster, Tag tag) throws UserException {
    for (Pair<String, Integer> pair : hostPortPairs) {
        if (getBackendWithHeartbeatPort(pair.first, pair.second) != null) {
            continue;
        }
    }

    for (Pair<String, Integer> pair : hostPortPairs) {
        addBackend(pair.first, pair.second, isFree, destCluster, tag);
    }
}
```
FE 中有个定时任务 HeartbeatMgr，该任务定期遍历 SystemInfoService 的字段 idToBackendRef 中记录的所有 backend，然后创建一个调用目标 backend heartbeat 函数的 RPC client，并且调用该 heartbeat
```java
// HeartbeatMgr.java
protected void runAfterCatalogReady() {
    List<Future<HeartbeatResponse>> hbResponses = Lists.newArrayList();
    
    // send backend heartbeat
    for (Backend backend : nodeMgr.getIdToBackend().values()) {
        BackendHeartbeatHandler handler = new BackendHeartbeatHandler(backend);
        hbResponses.add(executor.submit(handler));
    }

    ...
}

private class BackendHeartbeatHandler implements Callable<HeartbeatResponse> {   
    ...
    @Override
    public HeartbeatResponse call() {
        client = ClientPool.backendHeartbeatPool.borrowObject(beAddr);
        ...
        TMasterInfo copiedMasterInfo = new TMasterInfo(masterInfo.get());
        ...
        heartbeatRequest.setMasterInfo(copiedMasterInfo);
        THeartbeatResult result = client.heartbeat(heartbeatRequest);
        ...
    }
}
```
BE 实现了 HeartbeatServer。
```cpp
// heartbeat_server.cpp

```