# Recovery

Restore the database to the consistent state thst existsed before the failure.

## Recovery and Atomicity
To achieve our goal of atomicity, we must first output to stablee storage information describing the modification, without modifying the database itself.

## Shadow Paging
## Write-Ahead Logging

With write-ahead logging, the DBMS records all the changes made to the database in a log file (on stable storage) before the change is made to a disk page.

在 DBMS 能够将其修改的某个对象写回到 disk 上之前，DBMS 首先需要确保将 log file records 写入到磁盘。
配合 WAL，我们需要采取 STEAL + NO-FORCE 的 buffer pool management policy。

STEAL: "We are gonna to allow dirty pages on disks, as long as WAL is written to disk first."
NO-FORCE: 现在我们不要求 disk page is written before transaction is COMMITTED，而是要求 WAL is written before transaction is COMMITTED.


WAL 相比 Shadow Paging：
1. 写入性能更好
2. recovery 更慢

Log Entry:
* Transaction ID
* Object ID
* Before Value(For UNDO)
* After Value(For REDO)

For UNDO: 假如某个 Transaction 最终 ABORTED，那么我们需要将其修改的对象恢复，这叫 UNDO
For REDO: 加入某个 Transaction 在 COMMITTED 之后，没有在磁盘上记录最终的值，那么我们需要通过 Log 将最终的值在 recovery 阶段重现，这叫 REDO


### Database Modification
当一个 Transaction 需要修改某个磁盘上的对象时，需要经过如下步骤：
1. Transaction 在其私有内存空间进行计算
2. 修改 disk buffer in main memory 中包含该对象的 disk block（我理解这里是指 OS 的 page cache？）
3. 执行 output 操作将 disk block 写入到磁盘

我们称，某个 transaction modifies database 是指它对 disk buffer 进行了修改或者对磁盘本身进行了修改。

如果 database modification 发生在 transaction commit 时，那么称这种方式为 deferred-modification；如果发生在 transaction is still alive，那么称之为 immediate-modification

deferred-modification 要求 transaction 额外对所有需要更新的数据对象进行 local copy

### Concurrency Control and Recovery

## Recovery Algorithm
### Transaction Rollback
Transaction Abort 如何处理：
1. 反向遍历 log，对于其中 Ti 的每一条格式为 \<Ti, Xj, V1, V2> 的 log record：
   a. 将 Value V1 写入 data item Xj
   b. 在 log 中记录一条特殊的 redo-only log record \<Ti, Xj, V1>
2. 一旦找到 \<Ti start> 记录，那么 backward scan 就停止，然后写入 \<Ti abort>

### Recovery After a System Crash
解决系统重启后如何重现日志
1. In the redo phase, the system replays updates of all transactions by scanning the
log forward from the last checkpoint.  需要 replay 的 log 包含系统 crash 之前被 rolled back 的，以及尚未被 committed
    a. The list of transactions to be rolled back, undo-list, is initially set to the list L in the \<checkpoint L> log record.
    b. Whenever a normal log record of the form \<Ti, Xj, V1, V2>, or a redoonly log record of the form \<Ti, Xj, V2> is encountered, the operation is redone; that is, the value V2 is written to data item Xj.
    c. Whenever a log record of the form \<Ti start> is found, Ti is added to undo-list.
    d. Whenever a log record of the form \<Ti abort> or \<Ti commit> is found, Ti is removed from undo-list
    redo 阶段对所有 log record 执行 redone，这一过程可以保证所有应该完成 (COMMITTED+ABORT) 的 txn 都被完成，副作用有些正在执行的 txn 被错误地 redone，副作用需要交给 undo phrase 修正，这些需要被修正的 txn 被加入到 undo list 中
2. 在 undo phrase，反向遍历 log，对 undo-list 中的 txn 进行 roll back
   a. 一旦遇到某个 undo txn 的 record，perform undo action as if the log record had been found during the rollback of a failed transaction
   b. 当遇到\<Ti start>，那么就删除 undo-list 中的 Ti
   c. The undo phrase terminates once undo-list becomes empty.

### Optimizing Commit Processing

## Buffer Management
### Log-Record Buffering
Every log record is output to stable storage at the time it is created. Works but not good, high overhead.

Reason: 我们向磁盘写入时是按照 block 为单位的，在绝大多数情况下，a log record is much smaller than a block, 因此 each log record translates to a much larger output at the physical level.

Better method: Group commit.

We write log records to a log buffer in main memory. 但是这部分 log 在系统崩溃时由于来不及写入磁盘，会丢失。因此我们需要一些额外的过程保证：
* txn Ti 只有在 \<Ti commit> log 被写入磁盘后才会进入 COMMIT state
* 在 \<Ti commit> 被写入磁盘前，所有与 txn Ti 相关的 log records 都必须被写入磁盘
* Before a block of data in main memory can be output to the database (in nonvolatile storage), all log records pertaining to data in that block must have been output to stable storage.

以上被称为 write-ahead logging 规则。

### Database buffering

    Steal/No-Steal Force/No-Force

Steal: 是否允许 active txn 将 modification 写入磁盘
No-Steal: 不允许修改

No-Steal policy 无法处理当 txn 需要修改大量数据的情况：内存不足以保存所有数据。

Force: Transaction 在转变为`COMMITTED`之前，必须将所有修改写入 non-volatile storage
No-Force: 不是必须

Force writes make it easier to recover since all of the changes are preserved but result in poor runtime performance.

实现起来最简单的策略：No-Steal + Force 因为此时所有已经落盘的都是正确的状态，而所有中间状态均未落盘。恢复时不需要任何 UNDO 或者 REDO 操作。

实际上，几乎所有的数据库都采用 steal + no-force。

采用 steal 策略需要配合 WAL rule。比如有两个 transaction T0,T1，log file 状态为
\<T0 start>
\<T0, A, 1000, 950>
此时 T0 发起 read(B)。假设 B 所在的 block 不在内存，而此时内存 buffer pool 已经满了，bpm 选择 A 所在的 block 被换出。如果在 A 所在 block 被写入磁盘后，system crash occurs，那么 database 中 accounts A, B and C 的值为 950，2000，700, respectively. 此时 database 处于 inconsistent 状态。然而，由于 WAL rule 的第三条规则，我们在 output(A's block) 之前确保将之前的 log file 写入了磁盘。那么系统可以通过之前提到的 recovery algorithm 在重启时将 database 带回一致的状态。

When a block B1 is to be output to disk, all log records pertaining to data in B1 must be output to stable storage before B1 is output. 此过程中很重要的一点是，当 block 被 output 时，no writes to the block B1 be in progress. 实现该机制，我们需要为 block 设置一个互斥锁：
* Before a transaction performs a write on a data item, it acquires **an exclusive lock on the block in which the data item resides**. The lock is released immediately after the update has been performed.
* 当 block is to be output 时需要采取如下顺序：
  - obtain an exclusive lock on the block, to ensure that no txn is performing a write on the block
  - Output log records to stable storage until all log records pertaining to block B1 have been output
  - Output block B1 to disk
  - Release the lock once the block output has completed.

Database systems usually have a process that continually cycles through the buffer blocks, outputting modified buffer blocks back to disk. 这样可以使得 buffer pool 内的 dirty blocks 数量很少。

### Operating System Role in Buffer Management
操作系统使用磁盘上的 swap space 来缓存部分 main memory 的额外空间。在 DBMS 应用场景下，这可能导致额外的开销。假设一个 block Bx 被操作系统 output，那么它并不是被写入 database，而是被写入 swap space。当 dbms 需要 output Bx 时，那么 os 需要先从 swap space 将 Bx 读入，然后再 output to database