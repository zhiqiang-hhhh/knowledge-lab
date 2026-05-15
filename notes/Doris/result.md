对于每个 query，只有一个 result sink operator，并且这个 operator 所在的 fragment 也只有一个 instance。
所以一个 query 在 FE 上只有一个 Result Receiver 对象。

Fe 上 Coordinator 会构造一个 receiver
```java
public class StmtExecutor {
    ...
    private void sendResult(...) {
        ...
        // 读 PlanFragment 写 TPipelineFragmentParams
        // 写 reveiver
        // 读 TPipelineFragmentParams 写 rpc 
        coord.exec();   
        ...
        while(true) {
            ...
            batch = coord.getNext()
            ...
        }
    }
}

public class Coordinator {
    ...
    public void exec() throws Exception {
        ...

        QeProcessorImpl.INSTANCE.registerInstances(queryId, instanceIds.size());

        // create result receiver
        PlanFragmentId topId = fragments.get(0).getFragmentId();
        FragmentExecParams topParams = fragmentExecParamsMap.get(topId);
        DataSink topDataSink = topParams.fragment.getSink();
        this.timeoutDeadline = System.currentTimeMillis() + queryOptions.getExecutionTimeout() * 1000L;
        if (topDataSink instanceof ResultSink || topDataSink instanceof ResultFileSink) {
            TNetworkAddress execBeAddr = topParams.instanceExecParams.get(0).host;
            receiver = new ResultReceiver(queryId, topParams.instanceExecParams.get(0).instanceId,
                    addressToBackendID.get(execBeAddr), toBrpcHost(execBeAddr), this.timeoutDeadline);  
            ...
        }
    }

    public RowBatch getNext() {
        ...
        resultBatch = receiver.getNext(status);
        ...
    }
}

public class ResultReceiver {
    ...
    public RowBatch getNext(Status) {
        ...
        while(!isDone && !isCancel) {
            InternalService.PFetchDataRequest request;
            Future<InternalService.PFetchDataResult> future
                        = BackendServiceProxy.getInstance().fetchDataAsync(address, request);
            ...
            InternalService.PFetchDataResult pResult = null;
            while (pResult == null) {
                ...
                pResult = future.get(timeoutTs - currentTs, TimeUnit.MILLISECONDS);
            }
        }
    }
}
```


```proto
message PFetchDataRequest {
    required PUniqueId finst_id = 1;
    optional bool resp_in_attachment = 2;
};
```

BE 上每次 fetchData RPC 将会在 _heavy_work_threadpool 中增加一个 task，

```cpp
void PInternalServiceImpl::fetch_data(google::protobuf::RpcController* controller,
                                      const PFetchDataRequest* request, PFetchDataResult* result,
                                      google::protobuf::Closure* done) {
    bool ret = _heavy_work_pool.try_offer([this, controller, request, result, done]() {
        brpc::Controller* cntl = static_cast<brpc::Controller*>(controller);
        GetResultBatchCtx* ctx = new GetResultBatchCtx(cntl, result, done);
        _exec_env->result_mgr()->fetch_data(request->finst_id(), ctx);
    });
    if (!ret) {
        offer_failed(result, done, _heavy_work_pool);
        return;
    }
}

void ResultBufferMgr::fetch_data(const PUniqueId& finst_id, GetResultBatchCtx* ctx)
{
    TUniqueId tid;
    tid.__set_hi(finst_id.hi());
    tid.__set_lo(finst_id.lo());
    std::shared_ptr<BufferControlBlock> cb = find_control_block(tid);
    if (cb == nullptr) {
        LOG(WARNING) << "no result for this query, id=" << tid;
        ctx->on_failure(Status::InternalError("no result for this query"));
        return;
    }
    cb->get_batch(ctx);
}

std::shared_ptr<BufferControlBlock> ResultBufferMgr::find_control_block(const TUniqueId& instance_id) {
    // TODO(zhaochun): this lock can be bottleneck?
    std::lock_guard<std::mutex> l(_lock);
    BufferMap::iterator iter = _buffer_map.find(instance_id);

    if (_buffer_map.end() != iter) {
        return iter->second;
    }

    return std::shared_ptr<BufferControlBlock>();
}
```
看一下这个 BufferControlBlock 是啥时候构造的：
```cpp
Status ResultBufferMgr::create_sender(const TUniqueId& query_id, int buffer_size,
                                      std::shared_ptr<BufferControlBlock>* sender,
                                      bool enable_pipeline, int exec_timout)
{
    *sender = find_control_block(query_id);
    ...
    control_block = std::make_shared<PipBufferControlBlock>(query_id, buffer_size);
    
    {
        ...
        std::lock_guard<std::mutex> l(_lock);
        _buffer_map.insert(std::make_pair(query_id, control_block));
        int64_t max_timeout = time(nullptr) + exec_timout + 5;
        cancel_at_time(max_timeout, query_id);
    }
}

Status VResultSink::prepare(RuntimeState* state) {
    ...
    // create sender
    RETURN_IF_ERROR(state->exec_env()->result_mgr()->create_sender(
            state->fragment_instance_id(), _buf_size, &_sender, state->enable_pipeline_exec(),
            state->execution_timeout()));

    ...
    return Status::OK();
}
```
VResultSink 继承自 DataSink，统一在 DataSink 的工厂函数 create_data_sink 中进行构造，可以看到只会在 sink 类型为 RESULT_SINK 时才会构造 VResultSink 对象。

```cpp
Status DataSink::create_data_sink(ObjectPool* pool, const TDataSink& thrift_sink,
                                  const std::vector<TExpr>& output_exprs,
                                  const TPlanFragmentExecParams& params,
                                  const RowDescriptor& row_desc, RuntimeState* state,
                                  std::unique_ptr<DataSink>* sink, DescriptorTbl& desc_tbl)
{
    switch (thrift_sink.type) {
        case TDataSinkType::DATA_STREAM_SINK: {
            ...
        }
        case TDataSinkType::RESULT_SINK: {
            if (!thrift_sink.__isset.result_sink) {
                return Status::InternalError("Missing data buffer sink.");
            }

            // TODO: figure out good buffer size based on size of output row
            sink->reset(new doris::vectorized::VResultSink(row_desc, output_exprs,
                                                        thrift_sink.result_sink, 4096));
            break;
        }
        ...
    }
}

Status PipelineFragmentContext::prepare(const doris::TPipelineFragmentParams& request,
                                        const size_t idx)
{
    ...
    if (request.fragment.__isset.output_sink) {
        RETURN_IF_ERROR_OR_CATCH_EXCEPTION(DataSink::create_data_sink(
                _runtime_state->obj_pool(), request.fragment.output_sink,
                request.fragment.output_exprs, request, idx, _root_plan->row_desc(),
                _runtime_state.get(), &_sink, *desc_tbl));
    }
    ...
    RETURN_IF_ERROR(_build_pipelines(_root_plan, _root_pipeline));

}
```
也就是说在 `PipelineFragmentContext::prepare` 执行时，会构造 VResultSink 对象，该对象保存在 `PipelineFragmentContext::_sink` 中


### Buffer Control Block

```cpp
void ResultBufferMgr::fetch_data(const PUniqueId& finst_id, GetResultBatchCtx* ctx) {
    TUniqueId tid;
    tid.__set_hi(finst_id.hi());
    tid.__set_lo(finst_id.lo());
    std::shared_ptr<BufferControlBlock> cb = find_control_block(tid);
    if (cb == nullptr) {
        LOG(WARNING) << "no result for this query, id=" << tid;
        ctx->on_failure(Status::InternalError("no result for this query"));
        return;
    }
    cb->get_batch(ctx);
}

void BufferControlBlock::get_batch(GetResultBatchCtx* ctx) {
    std::lock_guard<std::mutex> l(_lock);
    if (!_status.ok()) {
        ctx->on_failure(_status);
        return;
    }
    if (_is_cancelled) {
        ctx->on_failure(Status::Cancelled("Cancelled"));
        return;
    }
    if (!_batch_queue.empty()) {
        // get result
        std::unique_ptr<TFetchDataResult> result = std::move(_batch_queue.front());
        _batch_queue.pop_front();
        _buffer_rows -= result->result_batch.rows.size();
        _data_removal.notify_one();

        ctx->on_data(result, _packet_num);
        _packet_num++;
        return;
    }
    if (_is_close) {
        ctx->on_close(_packet_num, _query_statistics.get());
        return;
    }
    // no ready data, push ctx to waiting list
    _waiting_rpc.push_back(ctx);
}
```
另一边，当有数据到来时:
```cpp
Status BufferControlBlock::add_batch(std::unique_ptr<TFetchDataResult>& result) {
    std::unique_lock<std::mutex> l(_lock);

    if (_is_cancelled) {
        return Status::Cancelled("Cancelled");
    }

    int num_rows = result->result_batch.rows.size();

    while ((!_fe_result_batch_queue.empty() && _buffer_rows > _buffer_limit) && !_is_cancelled) {
        _data_removal.wait_for(l, std::chrono::seconds(1));
    }

    if (_is_cancelled) {
        return Status::Cancelled("Cancelled");
    }

    if (_waiting_rpc.empty()) {
        // Merge result into batch to reduce rpc times
        if (!_fe_result_batch_queue.empty() &&
            ((_fe_result_batch_queue.back()->result_batch.rows.size() + num_rows) <
             _buffer_limit) &&
            !result->eos) {
            std::vector<std::string>& back_rows = _fe_result_batch_queue.back()->result_batch.rows;
            std::vector<std::string>& result_rows = result->result_batch.rows;
            back_rows.insert(back_rows.end(), std::make_move_iterator(result_rows.begin()),
                             std::make_move_iterator(result_rows.end()));
        } else {
            _fe_result_batch_queue.push_back(std::move(result));
        }
        _buffer_rows += num_rows;
    } else {
        auto ctx = _waiting_rpc.front();
        _waiting_rpc.pop_front();
        ctx->on_data(result, _packet_num);
        _packet_num++;
    }
    return Status::OK();
}

void GetResultBatchCtx::on_data(const std::unique_ptr<TFetchDataResult>& t_result,
                                int64_t packet_seq, bool eos) {
    Status st = Status::OK();
    if (t_result != nullptr) {
        uint8_t* buf = nullptr;
        uint32_t len = 0;
        ThriftSerializer ser(false, 4096);
        st = ser.serialize(&t_result->result_batch, &len, &buf);
        if (st.ok()) {
            _result->set_row_batch(std::string((const char*)buf, len));
            _result->set_packet_seq(packet_seq);
            _result->set_eos(eos);
        } else {
            LOG(WARNING) << "TFetchDataResult serialize failed, errmsg=" << st;
        }
    } else {
        _result->set_empty_batch(true);
        _result->set_packet_seq(packet_seq);
        _result->set_eos(eos);
    }
    st.to_protobuf(_result->mutable_status());
    { _done->Run(); }
    delete this;
}
```
执行的是 GetResultBatchCtx::on_data(...)，把一个 TFetchDataResult 对象序列化成 PFetchDataResult 的 row_batch 字段。并且添加一些其他的控制参数。



### 异常控制流

