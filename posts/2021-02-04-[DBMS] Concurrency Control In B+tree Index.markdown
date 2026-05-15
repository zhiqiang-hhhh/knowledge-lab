---
layout: post
title:  "Concurrency Control In B+tree Index"
date:   2021-02-04 14:50:11 +0800
categories: jekyll update
---
# B+ 树索引的并发控制
B+ 树是数据库索引的常用数据结构。本文不会介绍 B+ 树的实现，而是专注于对 B+ 树索引的并发控制。

我们知道，并发控制中最重要的用来管理共享资源的“东西”就是锁。在 B+ 树的并发控制中，理解锁的实现以及作用是非常重要的，这关系到我们最终实现的索引在使用时的效率。
所以我们先聊聊啥是锁🔒
## 锁是个什么“东西”

    Situations where two or more processes are reading or writing some shared data and the final result depends on who runs precisely when, are called race conditions.

在操作系统原理中，有对锁的最初启蒙，锁是作为解决竞态（Race Condition）的工具被提出的。锁实际上是一种互斥（Mutual exclusion）机制，该机制用于保证没有两个进程/线程能够同时进入临界区（Critical region）。为了实现这种机制有不同的方法：
### Mutual exclusion with busy waiting

    Busy waiting: Continuously testing a variable until some value appears is called busy waiting.

Busy waiting 的原理很简单，就是并发的线程持续不断地检测某个共享变量的值是否为某个期待值，如果满足期待，则说明当前线程可以进入临界区，否则就一直循环检测。在离开临界区时，线程将该共享变量的值恢复，以允许其他线程进入临界区。

Busy waiting 听起来很简单，似乎我们写一个如下循环即可：
```c
static bool could_inter = true;
while(!could_inter){
    ;
}
could_inter = false;
```
上述代码虽然逻辑上看起来能够满足我们的需要，但是注意，我们看到的并不是指令真正执行的样子。
当多个线程执行这段代码时，由于流水线机制，机器指令实际上是交错执行的。比如，变量`could_inter`在内存的进程虚拟地址空间的数据段，代码第 2 行语句检测该变量的值，这一过程从汇编代码看，起码需要两条指令：一条 mov 指令获取数据，另一条 cmp 或者类似的运算指令完成计算。当多个线程执行这段代码时，mov 指令与 cmp 指令之间就可能插入其他的 mov 或者 cmp 指令。此时已经出现了 race condition：两个线程同时访问了某个地址。

因此，busy waiting 的实现需要硬件的支持：硬件提供 TSL(Test and Set Lock)/CAS(Compare and Set) 指令支持。这类指令将原来需要多条指令配合才能完成的行为简化为一条指令，目的是防止在对共享的 lock-variable 检测期间发生线程/进程的切换。

在 C++ 标准库中提供了`std::atomic`库，用来调用 CAS 指令。

### Mutual exclusion with Sleep and Wakeup
Busy-waitings 实现的互斥锁问题在于并发的线程会一直占用 CPU 直到时间片用完，如果这些线程没有其他任务去做，那么在等待的这段时间完全是在空占 CPU。当临界区的访问会持续较长时间时，这种实现的效率不高。

C++ 标准库提供了`std::mutex`来提供互斥锁的另一种实现。mutex 只有两种状态：locked or unlocked。
当一个线程想要访问临界区时，首先调用 mutex_lock，如果 mutex 当前状态为 locked，则线程会被阻塞，直到另一个成功获取了 mutex 的线程将 mutex 的状态还原为 unlocked，操作系统将会随机将一个阻塞在该锁上的线程恢复。


## 读写锁
上述两类锁是从实现角度区分的，简单说，前者加锁失败后不会阻塞，后者会阻塞。而从功能划分上来说，还可以将锁与其他逻辑封装在一起，实现具有不同功能的锁。最典型的就是读写锁。

在数据库系统中，不同的线程往往具有不同的任务。有的比如查询线程只会读取索引以访问数据，有些执行写入/删除任务的线程则会修改索引结构。如果这两类线程都只使用统一的互斥锁，那么带来的问题就是：任何时刻只会有一个线程能够访问索引。很明显，我们期望的行为模式应该是：可以并发读，不能并发写。

为了提供这种访问索引的能力，我们需要将互斥锁封装一下，以读写锁的形式对外提供。

### 读写锁的逻辑
对于使用者来说，读写锁提供的逻辑很简单：
1. 读可以并发：同时有多个读线程同时读
2. 写必须互斥：任意时刻只能有一个写线程在写数据
3. 读写必须互斥：读和写不能并发，要获得读锁，必须确保没有线程在写；要获得写锁，必须确保没有线程在读。



### 读写锁的实现
```c++
#include <climits>
#include <condition_variable>
#include <mutex>               

class WriterReaderLock{
public:
    WriterReaderLock() = default;
    ~WriterReaderLock(){ std::lock_guard<mutex_> guard{mutex_}; }

    void WLock(){
        std::lock_guard<mutex_t> guard{mutex_};
        while(writer_entered_){
            reader_.wait(mutex_);
        }
        writer_entered_ = true;
        while(reader_count > 0){
            writer_.wait(mutex_);
        }
    }

    void WULock(){
        std::lock_guard<mutex_t> guard{mutex_};
        writer_entered_ = false;
        reader_.notify_all();
    }

    void RLock(){
        std::lock_guard<mutex_t> guard{mutex_};
        while(writer_entered || reader_count_ == MAX_READERS){
            reader_.wait(mutex_);
        }
        reader_count_++;
    }

    void RULock(){
        std::lock_guard<mutex_t> guard{mutex_};
        reader_count_--;
        if(writer_entered_){
            if(reader_count_ == 0){
                writer_.notify_one();
            }
        } else {
            if(reader_count_ == MAX_READERS - 1){
                reader_.notify_one();
            }
        }
    }

private:
    using mutex_t = std::mutex;
    using cond_t = std::condition_variable;
    static const uint32_t MAX_READERS = UINT_MAX;

    mutex_t mutex_;
    cond_t writer_;
    cond_t reader_;
    uint32_t reader_count_{0};
    bool writer_entered_{false};
};
```
从读写锁的实现来看其本质是对互斥锁的封装。
而且很容易理解，当我们使用场景是读多写少时，使用读写锁的效率肯定比单独互斥锁要高；如果是写多读少，那么读写锁相比互斥锁的效率优势会减少，当只有读没有写时，读写锁就完全退化为互斥锁。

另外，假如我们只有读没有写，那么读写锁其实也是低效的：这种情况下我们并不需要任何锁。
## B+ 树的并发访问

具体到 B+ 树的并发访问，一个最简单的方法是使用一个全局的锁来管理整个 B+ 树。这当然不是一个好的方法。

我们需要将锁的粒度降低到 Node 级别。此时，最直观的想法是，每当要要访问一个新节点，就获取一个该节点的读/写锁。当离开该节点后释放这个锁。

如果我们只有读操作，那毫无疑问这种方法是可行的，甚至加锁都多余了，啥锁都不需要。但是当发生多个写操作混合或者读写操作混合时，这种方案就会有问题。

比如在写入时，我们可能会分裂节点，分裂节点的过程是从下往上递归的，这就会导致两个线程的加锁顺序相反，当加锁路径重叠时最终一定会导致死锁。

出于提高效率以及避免死锁的角度考虑，需要保证：
1. 使用读写锁
2. 加锁方向相同

### Crabbing protocol

对于读操作：
* 首先对根节点加锁，当沿着树往下遍历时，首先对下一个子节点加锁，在对子节点加锁成功后，再释放父节点的锁。重复此过程直到到达叶子节点。

对于写操作（插入/删除）：
* 判断当前节点是否写安全（插入过程不可能分裂/删除过程不可能合并或者 rebalance）
* 如果写安全，则将所有祖先节点的锁释放，并对自己加写锁
* 如果写不安全，则对自己加写锁，继续访问下一个节点
* 如果当前节点为目标叶子节点，则开始写操作
* 如果有向上递归写操作，由于所有可能被修改的祖先节点已经被预先加锁，所以不再需要向上加锁
* 对于 sibling 节点，需要加锁

这套协议的关键是在寻找目标叶子节点的过程中根据当前节点是否写安全决定是否对其祖先加锁。
由于已经预先对会被修改的祖先节点按照从上往下的顺序加了锁，因此避免了死锁发生。

不过，对于向上递归过程中会访问到的 sibing 节点，依然需要加锁。但是此时对其加锁是安全的，因为祖先节点被加了写锁，其他线程无法与当前线程同时对 sibling 加写锁。

另外一点是还需要对根节点另外设置一个互斥锁，用于防止写操作会改变根节点的情况下，有其他线程在这期间进行读操作。

Crabbling protocol 只是描述了如何对 B+ 树进行从上到下的并发访问。实际 B+ 树实现时还会实现叶子结点的顺序遍历接口。该接口也需要进行并发控制。具体怎么做这里就不讲了，爷累了，感兴趣可以去查查相关资料。
