```c++
class TaskWorkerPool 
{
public:
    TaskWorkerPool(TaskWorkerType, ExecEnv, TMasterInfo, ThreadModel)
    {
        ...   
    }
    virtual void start();
    virtual void stop();
    virtual void submit_task(TAgentTaskRequest);

private:
    
}
```