```plantuml
TaskResource *-- SqlTaskManager
SqlTaskManager *-right- SqlTask

class TaskResource {
    - SqlTaskManager : taskManager
}

class SqlTaskManager {
    - TaskExecutor : taskExecutor
    - NonEvictableLoadingCache<TaskId, SqlTask> tasks;
    + updateTask(...) : TaskInfo
}

class SqlTask {
    - TaskId : taskID
    - Stirng : nodeId
    - AtomicReference<TaskHolder> : taskHolderReference
    + updateTask(...) : TaskInfo
}

SqlTask *-right- TaskExecution

class SqlTaskExecution {
    - remainingSplitRunners : AtomicLong
    - taskExecutor : TaskExecutor
}

class SqlTaskExecutionFactory {
    + create(...) : SqlTaskExecution
    - taskExecutor : TaskExecutor
}


```

### Prepare
WorkNode 在 prepare 阶段为每个 task 创建一个 SqlTaskExecution 数据结构，`SqlTaskExecution::start()` 会创建当前 task 需要的 driver。
```java
class SqlTask {
    private SqlTaskExecution tryCreateSqlTaskExecution(Session session, Span stageSpan, PlanFragment fragment)
    {
        SqlTaskExecution execution;
        execution = sqlTaskExecutionFactory.create(
                    session,
                    taskSpan.get(),
                    queryContext,
                    taskStateMachine,
                    outputBuffer,
                    fragment,
                    this::notifyStatusChanged);

        needsPlan.set(false);

        execution.start();
    }
}

class SqlTaskExecution {
    public synchronized void start()
    {
        try (SetThreadName _ = new SetThreadName("Task-" + getTaskId())) {
            ...
            // The scheduleDriversForTaskLifeCycle method calls enqueueDriverSplitRunner, which registers a callback with access to this object.
            // The call back is accessed from another thread, so this code cannot be placed in the constructor. This must also happen before outputBuffer
            // callbacks are registered to prevent a task completion check before task lifecycle splits are created
            scheduleDriversForTaskLifeCycle();
            // Output buffer state change listener callback must not run in the constructor to avoid leaking a reference to "this" across to another thread
            outputBuffer.addStateChangeListener(new CheckTaskCompletionOnBufferFinish(SqlTaskExecution.this));
        }
    }
}

```
```java
class SqlTaskExecution {
    private void scheduleDriversForTaskLifeCycle()
    {
        // This method is called at the beginning of the task.
        // It schedules drivers for all the pipelines that have task life cycle.
        List<DriverSplitRunner> runners = new ArrayList<>();
        for (DriverSplitRunnerFactory driverRunnerFactory : driverRunnerFactoriesWithTaskLifeCycle) {
            for (int i = 0; i < driverRunnerFactory.getDriverInstances().orElse(1); i++) {
                runners.add(driverRunnerFactory.createUnpartitionedDriverRunner());
            }
        }
        enqueueDriverSplitRunner(true, runners);
        for (DriverSplitRunnerFactory driverRunnerFactory : driverRunnerFactoriesWithTaskLifeCycle) {
            driverRunnerFactory.noMoreDriverRunner();
            verify(driverRunnerFactory.isNoMoreDriverRunner());
        }
        checkTaskCompletion();
    }

    private synchronized void enqueueDriverSplitRunner(boolean forceRunSplit, List<DriverSplitRunner> runners)
    {
        // schedule driver to be executed
        List<ListenableFuture<Void>> finishedFutures = taskExecutor.enqueueSplits(taskHandle, forceRunSplit, runners);
        // record new split runners
        remainingSplitRunners.addAndGet(runners.size());
        ...
    }
}
```
----
TODO: TaskExecutor 是进程级别的？

TaskExecutor 似乎是每个 work node 都只有一个，负责这个 work node 上所有 task 的执行
```java
public SqlTaskManager(
    ...
    TaskExecutor taskExecutor,
    ...)
{
    SqlTaskExecutionFactory sqlTaskExecutionFactory =
            new SqlTaskExecutionFactory(taskNotificationExecutor, taskExecutor, planner, splitMonitor, tracer, config);
}

public class SqlTaskExecutionFactory
{
    ...
    private final TaskExecutor taskExecutor;
    ...

    public SqlTaskExecution create(
            Session session,
            Span taskSpan,
            QueryContext queryContext,
            TaskStateMachine taskStateMachine,
            OutputBuffer outputBuffer,
            PlanFragment fragment,
            Runnable notifyStatusChanged)
    {
        ...

        return new SqlTaskExecution(
                    taskStateMachine,
                    taskContext,
                    taskSpan,
                    outputBuffer,
                    localExecutionPlan,
                    taskExecutor,
                    splitMonitor,
                    tracer,
                    taskNotificationExecutor);
    }
}
```
`SqlTaskExecution` 用到的 taskExecutor 来自 `SqlTaskManager`

-----

```java
public class TimeSharingTaskExecutor
        implements TaskExecutor
{
    private final ExecutorService executor;
    ...
    private final int runnerThreads;
    private final int minimumNumberOfDrivers;
    private final int guaranteedNumberOfDriversPerTask;
    private final int maximumNumberOfDriversPerTask;
    private final SortedSet<RunningSplitInfo> runningSplitInfos = new ConcurrentSkipListSet<>();
    @GuardedBy("this")
    private final List<TimeSharingTaskHandle> tasks;
    @GuardedBy("this")
    private final Set<PrioritizedSplitRunner> allSplits = new HashSet<>();
    /**
     * Splits running on a thread.
     */
    private final Set<PrioritizedSplitRunner> runningSplits = newConcurrentHashSet();
    ...

    @Override
    public List<ListenableFuture<Void>> enqueueSplits(TaskHandle taskHandle, boolean intermediate, List<? extends SplitRunner> taskSplits)
    {
        TimeSharingTaskHandle handle = (TimeSharingTaskHandle) taskHandle;
        List<PrioritizedSplitRunner> splitsToDestroy = new ArrayList<>();
        List<ListenableFuture<Void>> finishedFutures = new ArrayList<>(taskSplits.size());

        synchronized (this) {
            for (SplitRunner taskSplit : taskSplits) {
                TaskId taskId = handle.getTaskId();
                int splitId = handle.getNextSplitId();
                
                // add this to the work queue for the task
                if (handle.enqueueSplit(prioritizedSplitRunner)) {
                    // if task is under the limit for guaranteed splits, start one
                    scheduleTaskIfNecessary(handle);
                    // if globally we have more resources, start more
                    addNewEntrants();
                }
                else {
                    splitsToDestroy.add(prioritizedSplitRunner);
                }
                ...
            }
            recordLeafSplitsSize();
        }
        ...
        return finishedFutures;
    }

    private synchronized void scheduleTaskIfNecessary(TimeSharingTaskHandle taskHandle)
    {
        // if task has less than the minimum guaranteed splits running,
        // immediately schedule new splits for this task.  This assures
        // that a task gets its fair amount of consideration (you have to
        // have splits to be considered for running on a thread).
        int splitsToSchedule = min(guaranteedNumberOfDriversPerTask, taskHandle.getMaxDriversPerTask().orElse(Integer.MAX_VALUE)) - taskHandle.getRunningLeafSplits();
        for (int i = 0; i < splitsToSchedule; ++i) {
            PrioritizedSplitRunner split = taskHandle.pollNextSplit();
            if (split == null) {
                // no more splits to schedule
                return;
            }

            startSplit(split);
            splitQueuedTime.add(Duration.nanosSince(split.getCreatedNanos()));
        }
        recordLeafSplitsSize();
    }
}
```



```java

private synchronized void addNewEntrants()
{
    // Ignore intermediate splits when checking minimumNumberOfDrivers.
    // Otherwise with (for example) minimumNumberOfDrivers = 100, 200 intermediate splits
    // and 100 leaf splits, depending on order of appearing splits, number of
    // simultaneously running splits may vary. If leaf splits start first, there will
    // be 300 running splits. If intermediate splits start first, there will be only
    // 200 running splits.
    int running = allSplits.size() - intermediateSplits.size();
    for (int i = 0; i < minimumNumberOfDrivers - running; i++) {
        PrioritizedSplitRunner split = pollNextSplitWorker();
        if (split == null) {
            break;
        }

        splitQueuedTime.add(Duration.nanosSince(split.getCreatedNanos()));
        startSplit(split);
    }
}

private synchronized PrioritizedSplitRunner pollNextSplitWorker()
{
    // find the first task that produces a split, then move that task to the
    // end of the task list, so we get round robin
    for (Iterator<TimeSharingTaskHandle> iterator = tasks.iterator(); iterator.hasNext(); ) {
        TimeSharingTaskHandle task = iterator.next();
        // skip tasks that are already running the configured max number of drivers
        if (task.getRunningLeafSplits() >= task.getMaxDriversPerTask().orElse(maximumNumberOfDriversPerTask)) {
            continue;
        }
        PrioritizedSplitRunner split = task.pollNextSplit();
        if (split != null) {
            // move task to end of list
            iterator.remove();

            // CAUTION: we are modifying the list in the loop which would normally
            // cause a ConcurrentModificationException but we exit immediately
            tasks.add(task);
            return split;
        }
    }
    return null;
}
```

`minimumNumberOfDrivers` 的默认值是执行线程线程数的两倍，执行线程的默认值是CPU核数量的两倍。


所以任意时间，trino 会保证一个 work node 上进行 scan 
的 driver 数量不少于
