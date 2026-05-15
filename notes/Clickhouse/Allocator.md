
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Allocator](#allocator)
- [MemoryTracker](#memorytracker)
- [Arena](#arena)

<!-- /code_chunk_output -->



```plantuml
class MemoryTracker {
    - amount : atomic
    - peak : atomic
    - soft_limit : atomic
    - hard_limit : atomic
    - parent : std::atomic<MemoryTracker *>
    - allocImpl(size_t) : AllocationTrace
    - free(size_t) : AllocationTrace
}

struct AllocationTrace {
    + onAlloc() : void
    + onFree() : void
}

struct CurrentMemoryTracker {
    + {static} alloc(Int64 size) : AllocationTrace
    + {static} allocNoThrow(Int64 size) : AllocationTrace
    + {static} free(Int64 size) : AllocationTrace 
    - allocImpl(Int64 size) : AllocationTrace
}

CurrentMemoryTracker -- MemoryTracker : FriendClass

class Arena {
    + alloc() : char*
}

struct MemoryChunk {
    + prev : MemoryChunk*
}

MemoryChunk -up-> Allocator
Arena *-- MemoryChunk

class Allocator {
    + alloc(size_t size, size_t alignment = 0) : void *
    + free(void * buf, size_t size) : void 
}

Allocator *-- CurrentMemoryTracker : CurrentMemoryTracker 是一个 helper 类，所有方法都是 static
CurrentMemoryTracker *-- AllocationTrace
```

把内存分配分为两类，一类是自己主动使用`Arena`来管理起来的，比如 HashJoin 的 HashMap，还有 PodArray 这种数据容器。另一类则是通过 `malloc/free` 以及 `new/delete` 等操作符分配的内存。

### Allocator

`Allocator` 的 alloc 方法实现中会通过 `CurrentMemoryTracker` 这个 helper 类去调用当前线程的 `MemoryTracker::allocImpl`:
1. 更新内部的几个 atomic 变量
2. 判断内存使用是否超过限制
3. 返回一个 `AllocationTrace` 对象

`AllocationTrace` 也是一个 helper 类，这个类用于把内存分配相关的监控信息发送到指定的目的地，比如 `trace_log` 中
```cpp
template <bool clear_memory_, bool populate>
void * Allocator<clear_memory_, populate>::alloc(size_t size, size_t alignment)
{
    checkSize(size);
    auto trace = CurrentMemoryTracker::alloc(size);
    void * ptr = allocNoTrack<clear_memory_, populate>(size, alignment);
    trace.onAlloc(ptr, size);
    return ptr;
}
```
`Allocator` 通过 `Allocator::allocNoTrack` 来真正分配内存：
```cpp
template <bool clear_memory, bool populate>
void * allocNoTrack(size_t size, size_t alignment)
{
    ...
    buf = ::malloc(size);
    ...
    return buf;
}
```
### MemoryTracker
```cpp
MemoryTracker * getMemoryTracker()
{
    if (auto * thread_memory_tracker = DB::CurrentThread::getMemoryTracker())
        return thread_memory_tracker;

    /// Once the main thread is initialized,
    /// total_memory_tracker is initialized too.
    /// And can be used, since MainThreadStatus is required for profiling.
    if (DB::MainThreadStatus::get())
        return &total_memory_tracker;

    return nullptr;
}
```
`CurrentMemoryTracker` 这个 helper 类通过上面的方法获得属于当前线程的 `MemoryTracker`，如果当前线程没有创建 `MemoryTracker` 那么就会记录给主线程的 MemoryTracker。
```cpp
thread_local ThreadStatus constinit * current_thread = nullptr;

class ThreadStatus {
    ...
    MemoryTracker memory_tracker{VariableContext::Thread};

    ThreadStatus::ThreadStatus(bool check_current_thread_on_destruction_) {
        ...
        current_thread = this;
    }
}
```
线程在创建的时候会初始化自己的 ThreadStatus，比如通过 tcp 链接到 clickhouse server 的时候，worker 函数就会在运行的时候创建自己的 ThreadStatus：
```cpp
void TCPHandler::runImpl() {
    setThreadName("TCPHandler");
    ThreadStatus thread_status;
    ...
    TCPHandler::receiveQuery();
}

void TCPHandler::receiveQuery() {
    ...
    query_context = session->makeQueryContext(std::move(client_info));
    ...
}
```

**线程的 ThreadStatus 是如何跟 Query 绑定起来的？** 
```plantuml
class ThreadStatus {
    + attachToGroup(ThreadGroupPtr) : void
}

class ThreadGroup {
    + {static} createForQuery(QueryContext) : TaskGroup
    - query_context : Context
}

ThreadStatus --- ThreadGroup : attachToGroup 为当前线程记录所属的 ThreadGroup\n并且把当前线程的 MemTracker 的 parent 设置为 ThreadGroup 的 MemTracker
```
```cpp
TCPHandler::runImpl() {
    setThreadName("TCPHandler");
    ThreadStatus thread_status;
    ...
    /// Initialized later.
    std::optional<CurrentThread::QueryScope> query_scope;
    ...
    query_scope.emplace(query_context, /* fatal_error_callback */ [this]
    {
        std::lock_guard lock(fatal_error_mutex);
        sendLogs();
    });
}
```
QueryScope 的构造函数中接收一个 QueryContext，然后为当前 Query 查找/创建 相应的 ThreadGroup，并且把当前线程 attch 到相应的 ThreadGroup
```cpp
CurrentThread::QueryScope::QueryScope(ContextMutablePtr query_context, ...)
{
    auto group = ThreadGroup::createForQuery(query_context, ...);
    CurrentThread::attachToGroup(group);
}
```
`CurrentThread` 虽然是一个类，但是实际上它更像是一个 namespace。
```cpp
class CurrentThread {
    ...
    /// You must call one of these methods when create a query child thread:
    /// Add current thread to a group associated with the thread group
    static void attachToGroup(const ThreadGroupPtr & thread_group);
}

thread_local ThreadStatus constinit * current_thread = nullptr;

void CurrentThread::attachToGroup(const ThreadGroupPtr & thread_group)
{
    current_thread->attachToGroup(thread_group, true);
}
```
所以 `TCPHandler::runImpl` 执行到这里时，使用的 `current_thread` 就是它最开始执行时创建的 `ThreadStatus thread_status;`，同理，当当前线程的任务线程需要把自己跟 "Parent" 联系起来的时候，也可以使用类似的模式。
```cpp
void ThreadStatus::attachToGroupImpl(const ThreadGroupPtr & thread_group_)
{
    thread_group = thread_group_;
    thread_group->linkThread(thread_id);
    ...
    memory_tracker.setParent(&thread_group->memory_tracker);
    ...
}
```
### Arena
