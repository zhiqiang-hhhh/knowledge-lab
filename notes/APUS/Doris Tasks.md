# Doris Tasks
```plantuml
class AgentTaskQueue
{
    - {static} tasks
    + {static} addBatchTask(AgentBatchTask) : void
    + {static} addTask(AgentTask) : bool
}

class AgentTaskExecutor
{
    - {static} EXECUTOR : ExecutorService
    + {static} submit(AgentBatchTask)
}

class AgentBatchTask
{
    - backendIdToTasks : Map<Long, List<AgentTask>>
    + addTask(AgentTask) : void
    + {abstract} run () : void
}
```

```java
/// AgentBatchTask
public class AgentBatchTask implements Runnable {
    ...
    public void run() {
        for(Long backendId : this.backendIdToTasks.keySet()) {
            ...
            try {
                /// A
                Backend backend = Catalog.getCurrentSystemInfo().getBackend(backendId);
                if (backend == null || !backend.isAlive()) {
                    continue;
                }
            }
        }
    }
}
```
* A
  在 doris FE 中，add backends 是异步的。即当某个 AgentBatchTask 执行自己的 run 方法时，其目标 be 可能还未完成心跳建立。无法完成心跳建立的原因有多种，比如 1. IP:PORT 不合法；2. Be 未启动；3. 参数都合法，但是心跳还未来得及建立。因此这里如果 Be is not alive，则是选择忽略该be。