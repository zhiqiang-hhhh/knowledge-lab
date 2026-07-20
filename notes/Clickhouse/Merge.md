```cpp
void MergeTreeBackgroundExecutor<Queue>::routine(TaskRuntimeDataPtr item) {
    ...
    bool need_execute_again = false;

    try
    {
        need_execute_again = item->task->executeStep();
    }
    catch (...)
    {
        /// Release the task with exception context.
        /// An exception context is needed to proper delete write buffers without finalization
        cancel_task(std::move(item));
        return;
    }

    if (!need_execute_again)
    {
        complete_task(std::move(item));
        return;
    }

    restart_task(std::move(item));
}
```
```
```


110: vol-07c1d3978e1a09f6a
167: vol-01c4105b77176360f
241: vol-0ac12be629ef07a60