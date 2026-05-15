
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [11.5 Thread Termination](#115-thread-termination)
- [11.6 Thread Synchronization](#116-thread-synchronization)
  - [11.6.1 Mutexes](#1161-mutexes)
  - [11.6.2 Deadlock Avoidance](#1162-deadlock-avoidance)

<!-- /code_chunk_output -->

## 11.5 Thread Termination
如果进程的任何线程调用了`exit`,  `_Exit`, 或者`_exit`，那么整个进程就会终止。  

对于一个线程来说有三种退出方式，通过这三种方式可以结束自己的控制流而不会终止整个进程。  

1. 线程直接返回到起始程序。返回值是线程的`exit code`
2. 线程可以由进程中的其他线程取消
3. 线程调用`pthread_exit`

```c
void pthread_exit(void *rval_ptr);
```
`rval_ptr`是一个 void 指针。这个指针对进程中的其他线程来说是可用的，其他线程可以通过`pthread_join`函数来获得`rval_ptr`指向的内容。
```c
int pthread_join(pthread_t thread, void ** rval_ptr);
```
The calling thread will block untill the specified thread calls `pthread_exit`, returns from its start routine, or is caceled.
如果线程是从它的 start routine 中以 return 结束，那么其 return 值将会保存在`rval_ptr`中。如果线程被取消，那么 `rval_ptr`所指向内存位置中的值将会存放`PTHREAD_CANCELED`
```c
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <pthread.h>
void *thr_fn1(void *arg)
{
    printf("thread 1 returning\n");
    return ((void *)1);
}

void *thr_fn2(void *arg)
{
    printf("thread 2 exiting\n");
    pthread_exit((void *)2);
}

int main()
{
    int err;
    pthread_t tid1, tid2;
    void *tret;

    err = pthread_create(&tid1, NULL, thr_fn1, NULL);
    if (err != 0)
        write(3, "can't create thread 1 ", sizeof("can't create thread 1 "));

    err = pthread_create(&tid2, NULL, thr_fn2, NULL);
    if (err != 0)
        write(3, "can't create thread 2 ", sizeof("can't create thread 2 "));
    
    err = pthread_join(tid1, &tret);
    if (err != 0)
        write(3, "can't join with thread 1 ", sizeof("can't join with thread 1 "));
    printf("thread 1 exit code %ld\n", (long)tret);

    err = pthread_join(tid2, &tret);
    if (err != 0)
        write(3, "can't join with thread 2 ", sizeof("can't join with thread 2 "));
    printf("thread 2 exit code %ld\n", (long)tret);

    exit(0);
}
```
```bash
hzq0@ubuntu:~/Documents/OS/multithread$ ./thread_termination 
thread 1 returning
thread 2 exiting
thread 1 exit code 1
thread 2 exit code 2
```

传递给`pthread_create`和`pthread_exit`的void 指针可以用来指向更复杂的结构，传递更多的信息。

注意，用于这个structure的内存空间在 caller 结束之后依然可用。  
比如，如果调用者在它的栈中创建了一个 structure ，那么当这个结构体再被使用时，其中的内容可能已经发生了改变。


如果有个线程在它的栈中分配了一个 structure 然后向`pthread_exit`传递了这个结构体的地址，然后该线程的`stack`被清空，那么当 `caller of pthread_join `尝试使用这个结构体时，就会出现问题。
```c
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

struct foo
{
    int a, b, c, d;
};

void printfoo(const char *s, const struct foo *fp)
{
    printf("%s", s);
    printf(" structure at 0x%lx\n", (unsigned long)fp);
    printf(" foo.a = %d\n", fp->a);
    printf(" foo.b = %d\n", fp->b);
    printf(" foo.c = %d\n", fp->c);
    printf(" foo.d = %d\n", fp->d);
}

void *thr_fn1(void *arg)
{
    struct foo foo = {1, 2, 3, 4};

    printfoo("thread 1: \n", &foo);
    pthread_exit((void *)&foo);
}

void *thr_fn2(void *arg)
{
    printf("thread 2: ID is %lu\n", (unsigned long)pthread_self());
    pthread_exit((void *)0);
}

int main(void)
{
    int err;
    pthread_t tid1, tid2;
    struct foo *fp;

    printfoo("parent: \n", fp);

    err = pthread_create(&tid1, NULL, thr_fn1, NULL);
    if (err != 0)
        write(3, "can't create thread 1", sizeof("can't create thread 1"));

    err = pthread_join(tid1, (void *)&fp);
    if (err != 0)
        write(3, "can't join with thread 1", sizeof("can't join with thread 1"));

    sleep(1);
    printf("parent starting second thread\n");
    err = pthread_create(&tid2, NULL, thr_fn2, NULL);
    if (err != 0)
        write(3, "can't create thread 2", sizeof("can't create thread 2"));

    sleep(1);
    printfoo("parent: \n", fp);
    exit(0);
}
```
```bash
parent: 
 structure at 0x7ffc17025c60
 foo.a = 1
 foo.b = 0
 foo.c = 386031846
 foo.d = 32764
thread 1: 
 structure at 0x7efe8e325f30
 foo.a = 1
 foo.b = 2
 foo.c = 3
 foo.d = 4
parent starting second thread
thread 2: ID is 139631772460800
parent: 
 structure at 0x7efe8e325f30
 foo.a = -1905362688
 foo.b = 32510
 foo.c = -1907769022
 foo.d = 32510
```
`structure *fp` 在 parent thread 中的值为 `0x7ffc17025c60`，对应内存中的值为随机分配。  
 thread 1 调用 pthread_exit 将自己的 structure foo 指针返回，在thread 1 中 该 foo 中的内容为
 ```
 foo.a = 1
 foo.b = 2
 foo.c = 3
 foo.d = 4
 ```
该 structure foo 分配在 thread 1 的 stack 中，当 thread 1 终止后，它的 stack 被清空。当 parent thread 能够使用 fp 时， fp 指向 thread 1 中的 structure foo 的地址，而此时该内存空间已经被清空，所以在 parent thread 中看到的 struct foo 为随机值
```
parent: 
 structure at 0x7efe8e325f30
 foo.a = -1905362688
 foo.b = 32510
 foo.c = -1907769022
 foo.d = 32510
```

为了解决这个问题，我们既可以使用一个全局的结构体，或者使用`malloc`来创建结构体。

线程可以通过调用`pthread_cancle`来取消同一个进程中的另一个线程
```c
int pthread_cancle(pthread_t tid);
```
在默认情况下，`tid`表示的线程执行的动作就像自己主动调用`pthread_exit`，返回的参数为`PTHREAD_CANCELED`。然而线程可以选择无视或者控制它如何被取消。注意，`pthread_cancle`不会等待线程被结束，而只是进行一次取消请求而已。

线程可以安排当它推出时执行的函数，方法与 `atexit`相似。这些函数叫做`thread cleanup handlers`。每个线程可以具有多个`cleanup handler`。处理函数被记录在栈中，意味着他们执行的顺序与注册的顺序相反
```c
void pthread_cleanup_push(void (*rtn)(void *), void *arg);
void pthread_cleanup_pop(int execute);
```

`rtn`参数为被执行的函数，`arg`用来传参。当线程执行以下动作时，`pthread_cleanup_push`函数将会作用。
* 调用`pthread_exit`
* 响应一个取消请求
* 使用`nonzero execute argument`来调用`pthread_cleanup_pop`函数

如果`execute`参数被设置为0，`cleanup`函数就不会被调用。不过不论是哪种情况，`pthread_cleanup_pop`函数都会移除最近一个`pthread_cleanup_push`函数压入的处理程序。  

这两个函数的一个限制在于，由于他们是通过宏实现的，所以他们必须在同一个 thread 内成对出现。
```c
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>

void cleanup(void *arg)
{
    printf("cleanup: %s \n", (char *)arg);
}

void *thr_fn1(void *arg)
{
    printf("thread 1 start\n");
    pthread_cleanup_push(cleanup, "thread 1 first handler");
    pthread_cleanup_push(cleanup, "thread 1 second handler");
    printf("thread 1 push complete\n");
    if (arg)
        return ((void *)1);
    pthread_cleanup_pop(1);
    pthread_cleanup_pop(1);
    return ((void *)1);
}

void *thr_fn2(void *arg)
{
    printf("thread 1 start\n");
    pthread_cleanup_push(cleanup, "thread 2 first handler");
    pthread_cleanup_push(cleanup, "thread 2 second handler");
    printf("thread 2 push complete\n");
    if (arg)
        pthread_exit((void *)2);
    pthread_cleanup_pop(1);
    pthread_cleanup_pop(1);
    return ((void *)2);
}

int main(void)
{
    int err;
    pthread_t tid1, tid2;
    void *tret;

    err = pthread_create(&tid1, NULL, thr_fn1, (void *)1);
    err = pthread_create(&tid2, NULL, thr_fn2, (void *)2);

    err = pthread_join(tid1, &tret);
    printf("thread 1 exit code %ld\n", (long)tret);

    err = pthread_join(tid2, &tret);
    printf("thread 2 exit code %ld\n", (long)tret);

    exit(0);
}
```
```
thread 1 start
thread 1 push complete
thread 1 start
thread 2 push complete
thread 1 exit code 1
cleanup: thread 2 second handler 
cleanup: thread 2 first handler 
thread 2 exit code 2
```
当线程从其`first routine`中返回时，不会调用 cleanup handler ，如果是以`pthread_exit`结束，那么之前`pthraed_cleanup_push`过的处理函数将会被执行。


默认情况下，一个线程的结束信息将会一直保存，直到我们为该线程调用了`pthread_join`函数。线程的隐藏存储空间可以在结束时立刻被回收，如果线程是被`detached`。
```c
int pthread_detach(pthread_t tid);
```
在线程被`detached`之后，我们不可以使用`pthread_join`函数来等待它的结束状态信息，因为该信息已经被回收。

## 11.6 Thread Synchronization
On processor architectures in which the modification takes more than one memory cycle, this can happen when the memory read is interleaved between the memory write cycles.

### 11.6.1 Mutexes
互斥量变量由一个`pthread_mutex_t`数据类型来表示。在使用一个 mutex 变量之前，首先需要将它提前初始化为常量`PTHREAD_MUTEX_INITIALIZER` (仅仅用于静态分配的mutex)。如果我们动态分配 mutex ，那么需要在释放内存之前调用 `pthread_mutex_destory`

```c
int pthread_mutex_init(pthread_mutex_t *restrict mutex, const pthread_mutexattr_t *restrict attr);

int pthread_mutex_destory(pthread_mutex_t *mutex);
```

To lock a mutex, 调用 `pthread_mutex_lock`. 如果 mutex 已经被锁，那么 calling thread 将会阻塞，直到 mutex 被释放。
```c
int pthread_mutex_lock(pthread_mutex_t *mutex);
int pthread_mutex_trylock(pthread_mutex_t *mutex);
int pthread_mutex_unlock(pthread_mutex_t *mutex);
```
如果线程不打算阻塞，那么可以有条件地使用`pthread_mutex_trylock`来对 mutex 加锁。

使用 mutex 保护数据结构的例子：
```c
#include <stdlib.h>
#include <stdio.h>
#include <pthread.h>

struct foo
{
    int f_count;
    pthread_mutex_t f_lock;
    int f_id;
};

struct foo *foo_alloc(int id)
{
    struct foo *fp;
    if ((fp = malloc(sizeof(struct foo))) != NULL)
    {
        fp->f_count = 1;
        fp->f_id = id;
        if (pthread_mutex_init(&fp->f_lock, NULL) != 0)
        {
            free(fp);
            return (NULL);
        }
    }
    return (fp);
}

void foo_hold(struct foo *fp)
{
    pthread_mutex_lock(&fp->f_lock);
    fp->f_count++;
    pthread_mutex_unlock(&fp->f_lock);
}

void foo_rele(struct foo *fp)
{
    pthread_mutex_lock(&fp->f_lock);
    if (--fp->f_count == 0)
    {
        pthread_mutex_unlock(&fp->f_lock);
        pthread_mutex_destroy(&fp->f_lock);
        free(fp);
    }
    else
    {
        pthread_mutex_unlock(&fp->f_lock);
    }
}
```
foo struct 可能被多个线程并发访问，因此每个线程对其中的数据成员进行操作之前都需要首先获得 mutex ，保证控制流不会交叉。

在使用对象之前，线程需要线调用 foo_hold 来添加一个对它的引用。当对对象的使用完成之后，必须要调用 foo_rele 来释放引用。当最后一个引用被释放之后，表示没有线程在使用对象，那么就清空对象。

但是在这里例子中，我们忽视了线程在调用 foo_hold 之前是如何寻找对象的。如果有另一个线程在调用 foo_hold 之时被阻塞，那么即使引用计数为 0 ，对于 foo_rele 来说清空对象的内存空间可能会导致出错。

### 11.6.2 Deadlock Avoidance
通过小心调整加锁的顺序可以避免死锁。比如需要同时对 A 和 B 两个资源加锁，如果所有使用资源的线程都保证在对 B 加锁之前先对 A 加锁，那么就不会发生死锁。

```c
#include <stdlib.h>
#include <pthread.h>

#define NHASH 29
#define HASH(id) (((unsigned long)id) % NHASH)

struct foo *fh[NHASH];

pthread_mutex_t hashlock = PTHREAD_MUTEX_INITIALIZER;

struct foo
{
    int f_count;
    pthread_mutex_t f_lock;
    int f_id;
    struct foo *f_next;
};

struct foo *foo_alloc(int id)
{
    struct foo *fp;
    int idx;

    if ((fp = malloc(sizeof(struct foo))) != NULL)
    {
        fp->f_count = 1;
        fp->f_id = id;
        if (pthread_mutex_init(&fp->f_lock, NULL) != 0)
        {
            free(fp);
            return (NULL);
        }
        idx = HASH(id);
        pthread_mutex_lock(&hashlock);
        fp->f_next = fh[idx];
        fh[idx] = fp;
        pthread_mutex_lock(&fp->f_lock);
        pthread_mutex_unlock(&hashlock);

        pthread_mutex_unlock(&fp->f_lock);
    }
    return (fp);
}

void foo_hold(struct foo *fp)
{
    pthread_mutex_lock(&fp->f_lock);
    fp->f_count++;
    pthread_mutex_unlock(&fp->f_lock);
}

struct foo *foo_find(int id)
{
    struct foo *fp;

    pthread_mutex_lock(&hashlock);
    for (fp = fh[HASH(id)]; fp != NULL; fp = fp->f_next)
    {
        if (fp->f_id == id)
        {
            foo_hold(fp);
            break;
        }
    }
    pthread_mutex_unlock(&hashlock);
    return (fp);
}

void foo_rele(struct foo *fp)
{
    struct foo *tfp;
    int idx;

    pthread_mutex_lock(&fp->f_lock);
    if (fp->f_count == 1)
    {
        pthread_mutex_unlock(&fp->f_lock);
        pthread_mutex_lock(&hashlock);
        pthread_mutex_lock(&fp->f_lock);

        if (fp->f_count != 1)
        {
            fp->f_count--;
            pthread_mutex_unlock(&fp->f_lock);
            pthread_mutex_unlock(&hashlock);
            return;
        }

        idx = HASH(fp->f_id);
        tfp = fh[idx];
        if (tfp == fp)
        {
            fh[idx = fp->f_next];
        }
        else
        {
            while (tfp->f_next != fp)
                tfp = tfp->f_next;

            tfp->f_next = fp->f_next;
        }
        pthread_mutex_unlock(&hashlock);
        pthread_mutex_unlock(&fp->f_lock);
        pthread_mutex_destroy(&fp->f_lock);
        free(fp);
    }
    else
    {
        fp->f_count--;
        pthread_mutex_unlock(&fp->f_lock);
    }
}
```

这段代码新增加了一个 散列表 用来追踪 struct foo ，`hashlock` 用来保护 `fh` 和 `f_next`，`foo_find`函数解决了前一节最后提出的问题。因为 `hashlock`保证了对 `fh` 的控制流不会交叉，因此在当前线程因为 `pthread_mutex_lock(&fp->lock)` 而阻塞以后，不会出现其他线程将目标 struct foo 清空的冲突。

当然，这段程序也因为引入了两个互斥锁而导致有的部分显得很复杂，考虑设计逻辑以后，可以使用 `hashlock` 同时保护 `the structure reference count`, 而`structure mutex`则负责保护`foo struct`中的其他成员。
```c
#include <stdlib.h>
#include <pthread.h>
#define NHASH 29
#define HASH(id) (((unsigned long)id) % NHASH)
struct foo *fh[NHASH];
pthread_mutex_t hashlock = PTHREAD_MUTEX_INITIALIZER;
struct foo
{
    int f_count; /* protected by hashlock */
    pthread_mutex_t f_lock;
    int f_id;
    struct foo *f_next; /* protected by hashlock */
    /* ... more stuff here ... */
};
struct foo *
foo_alloc(int id) /* allocate the object */
{
    struct foo *fp;
    int idx;
    if ((fp = malloc(sizeof(struct foo))) != NULL)
    {
        fp->f_count = 1;
        fp->f_id = id;
        if (pthread_mutex_init(&fp->f_lock, NULL) != 0)
        {
            free(fp);
            return (NULL);
        }
        idx = HASH(id);
        pthread_mutex_lock(&hashlock);
        fp->f_next = fh[idx];
        fh[idx] = fp;
        pthread_mutex_lock(&fp->f_lock);
        pthread_mutex_unlock(&hashlock);
        /* ... continue initialization ... */
        pthread_mutex_unlock(&fp->f_lock);
    }
    return (fp);
}
void foo_hold(struct foo *fp) /* add a reference to the object */
{
    pthread_mutex_lock(&hashlock);
    fp->f_count++;
    pthread_mutex_unlock(&hashlock);
}
struct foo *
foo_find(int id) /* find an existing object */
{
    struct foo *fp;
    pthread_mutex_lock(&hashlock);
    for (fp = fh[HASH(id)]; fp != NULL; fp = fp->f_next)
    {
        if (fp->f_id == id)
        {
            fp->f_count++;
            break;
        }
    }
    pthread_mutex_unlock(&hashlock);
    return (fp);
}
void foo_rele(struct foo *fp) /* release a reference to the object */
{
    struct foo *tfp;
    int idx;
    pthread_mutex_lock(&hashlock);
    if (--fp->f_count == 0)
    { /* last reference, remove from list */
        idx = HASH(fp->f_id);
        tfp = fh[idx];
        if (tfp == fp)
        {
            fh[idx] = fp->f_next;
        }
        else
        {
            while (tfp->f_next != fp)
                tfp->f_next = fp->f_next;
        }
        pthread_mutex_unlock(&hashlock);
        pthread_mutex_destroy(&fp->f_lock);
        free(fp);
    }
    else
    {
        pthread_mutex_unlock(&hashlock);
    }
}
```