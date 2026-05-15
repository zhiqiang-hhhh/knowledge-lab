### 本地文件组织




## 同步机制
原生的Clickhouse依赖本地文件系统保存很多 part 状态信息，比如 DETACH PARTITION 的时候将目标 part 全部 move 到 `storage.relative_path/detached/` 下，通过 detached 目录来记录 DETACH 行为，并没有另一个集中的元数据文件来记录 part 的状态。

StorageShareDiskMergeTree 依赖 manifest 来记录所有的行为，依赖 snapshot 来记录某个时间点 table 元数据的快照。所以如果让我们从头开始实现 StorageSharedDisk，就可以不再需要本地的目录组织结构了，所有的 part 状态都记录在 snapshot + manifest 中，part 与数据文件（共享文件系统上的文件/对象存储上的对象）的映射关系都以 protobuf 的消息格式持久化到 manifest 中，具体指 CHPartMetaPB。

但是由于我们是在 Clickhouse 的基础上，通过继承 MergeTreeData，构造了 StorageShareDiskMergeTree，而 MergeTreeData 以及 IMergeTreeDataPart 的很多操作都是默认 part 被保存在某个 IDisk 指向的本地文件系统上，所以我们在 StorageMergeTree 实现时，也需要保留本地文件系统上 part 的目录。但是，这里保存本地文件系统的组织结构，只是为了兼容原有的 Clickhouse 代码逻辑，我们不依赖本地文件系统记录元信息。比如 ATTACH PARTITION 的时候，我们是从 CHTableManifestPB.detached_parts 中获取之前所有被 detach 过的 part，而不是通过本地文件系统的 detached 目录，哪怕 detached 目录下也有我们想要的信息。


### 原子操作

在并发编程的时候，我们提出了原子操作来实现不同进程/线程之间的同步。原子操作是提供一种机制，能够确保在进程 P1 访问某个临界资源（包括一切共享资源，内存、磁盘等）期间，该临界资源不会被其他进程访问。
以内存操作为例，原子操作实现的原理是在进程 P1 执行原子操作 A 期间，将访问这段内存的 memory bus 加锁，确保即使发生了进程切换，或者其他核上的线程想要访问这段内存，这段内存中的数据对于进程 P1 始终是一致的。

在我们的 StorageSharedDisk 中，不同副本之间共享 manifest，而不同副本之间又是等价的，那么我们对 manifest 的操作就是临界区，我们需要一个机制来确保 manifest 对于不同进程是来说是一致的。

manifest 本质是 snopshot + redo log。我们对 manifest 的操作可以分为两类：
1. 先获取最新的 manifest，然后本地进程决定怎么执行某个操作，然后再添加 redo log，冲突后尝试获取最新的 manifest，直到成功，最后再真正执行该操作，典型操作: ATTACH PARTITION，DROP DETACHED
2. 先在本地决定如何操作，然后添加 redo log，如果发生了冲突，获取最新的 manifest，再重试，直到成功。典型操作: INSERT，DETACH PARTITION

这两类操作的区别在于：
1. **前者执行前需要先获取最新的 manifest，而后者则先默认自己的内存状态是最新的**。
    以 ATTACH PARTITION 为例，我们需要先知道有哪些 DETACHED PARTS，才能决定 ATTACH 的对象是哪些，而 DETACHED PARTS 这个信息不会保存在 BE 进程内存中，只记录在 manifest 里；后者则是类似乐观锁（存疑），认为自己内存状态是最新的，只有当 append manifest 冲突的时候，才会通过最新的 manifest 更新自己的内存状态
1. **前者真正执行操作（指修改磁盘文件）是在添加最新 redo log 成功后，而后者在添加 redo log 之前就已经完成了磁盘上的动作**。
    以 ATTACH PARTITION 为例，当我们通过 manifest 更新自己的内存状态，并且添加 redo log 之后，我们就可以认为，在此时，执行 ATTACH 才会是正确的，能够保证不同副本在执行 redo log 后，内存与磁盘上状态一致，如果在添加 log 之前就操作磁盘，那么一旦添加 log 失败，我们之前对磁盘的操作可能就是错误的。
    后者为何可以在添加log之前就操作磁盘？是因为我们保证了，磁盘上的数据一定是正确的。比如对于 INSERT，我们在本地保存的 part 文件名为其 uuid，而不是 name。name 在冲突过程中是可能会被改变的，而 uuid 则永远不会变。

### 冲突解决
