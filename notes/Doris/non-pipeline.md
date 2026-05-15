```cpp
Status FragmentMgr::exec_plan_fragment(const TExecPlanFragmentParams& params,
                                       const FinishCallback& cb)
{
    ...
    auto fragment_executor =
            std::make_shared<PlanFragmentExecutor>(
                            _exec_env, query_ctx,
                            params.params.fragment_instance_id, -1,
                            params.backend_num,
                            std::bind<void>(
                                std::mem_fn(
                                    &FragmentMgr::coordinator_callback),
                                    this, 
                                    std::placeholders::_1));
    ...
    RETURN_IF_ERROR(fragment_executor->prepare(params));
    
    _fragment_map.insert(std::make_pair(
        params.params.fragment_instance_id, fragment_executor));
    
    auto st = _thread_pool->submit_func(
            [this, fragment_executor, cb] {
                _exec_actual(fragment_executor, cb);
            });
    ...

}

void FragmentMgr::_exec_actual(std::shared_ptr<PlanFragmentExecutor> fragment_executor,
                               const FinishCallback& cb)
{
    ...
    Status st = fragment_executor->execute();
    if (!st.ok()) {
        fragment_executor->cancel(PPlanFragmentCancelReason::INTERNAL_ERROR,
                                  "fragment_executor execute failed");
    }
    /// 不论 fragment_executor 是正常执行完还是异常执行完
    /// 都是用的是相同的退出流程？
    std::shared_ptr<QueryContext> query_ctx = fragment_executor->get_query_ctx();
    bool all_done = false;
    if (query_ctx != nullptr) {
        // decrease the number of unfinished fragments
        all_done = query_ctx->countdown(1);
    }

    // remove exec state after this fragment finished
    {
        std::lock_guard<std::mutex> lock(_lock);
        _fragment_map.erase(fragment_executor->fragment_instance_id());
        if (all_done && query_ctx) {
            _query_ctx_map.erase(query_ctx->query_id());
        }
    }

    // Callback after remove from this id
    auto status = fragment_executor->status();
    cb(fragment_executor->runtime_state(), &status);
}

Status PlanFragmentExecutor::execute() {
    ...
    {
        ...
        Status st = open();
        if (!st.ok()) {
            cancel(PPlanFragmentCancelReason::INTERNAL_ERROR,
                   fmt::format("PlanFragmentExecutor open failed, reason: {}", st.to_string()));
        }
        close();
    }
    ...
}

Status PlanFragmentExecutor::open() {

}
```

ExchangeNode 的 open 
```cpp {.line-numbers}
Status VExchangeNode::open(RuntimeState* state) {
    SCOPED_TIMER(_runtime_profile->total_time_counter());
    RETURN_IF_ERROR(ExecNode::open(state));
    return Status::OK();
}

ExecNode::open -> alloc_resource -> VExchangeNode::alloc_resource

Status VExchangeNode::alloc_resource(RuntimeState* state) {
    RETURN_IF_ERROR(ExecNode::alloc_resource(state));
    if (_is_merging) {
        RETURN_IF_ERROR(_vsort_exec_exprs.open(state));
        if (!state->enable_pipeline_exec()) {
            RETURN_IF_ERROR(
                _stream_recvr->create_merger(
                    _vsort_exec_exprs.lhs_ordering_expr_ctxs(), 
                    _is_asc_order, _nulls_first,
                    state->batch_size(), _limit, _offset));
        }
    }
    return Status::OK();
}

Status VDataStreamRecvr::create_merger(...) {
    ...
    std::vector<BlockSupplier> child_block_suppliers;
    // Create the merger that will a single stream of sorted rows.
    _merger.reset(new VSortedRunMerger(ordering_expr, is_asc_order, nulls_first, batch_size, limit, offset, _profile));

    for (int i = 0; i < _sender_queues.size(); ++i) {
        child_block_suppliers.emplace_back(std::bind(std::mem_fn(&SenderQueue::get_batch),
                                                     _sender_queues[i], std::placeholders::_1,
                                                     std::placeholders::_2));
    }
    _merger->set_pipeline_engine_enabled(_enable_pipeline);
    RETURN_IF_ERROR(_merger->prepare(child_block_suppliers));
}

VSortedRunMerger::prepare(const vector<BlockSupplier>& input_runs) {
    ...
    for (const auto& supplier : input_runs) {
        ...
        _cursors.emplace_back(supplier, _ordering_expr, _is_asc_order, _nulls_first);
    }
}

struct BlockSupplierSortCursorImpl : public MergeSortCursorImpl {
    BlockSupplierSortCursorImpl(const BlockSupplier& block_supplier,
                                const VExprContextSPtrs& ordering_expr,
                                const std::vector<bool>& is_asc_order,
                                const std::vector<bool>& nulls_first)
    ... {
        ...
        _is_eof = !has_next_block();
    }

    bool has_next_block() override {
        do {
            status = _block_supplier(&_block, &_is_eof);
        } while (_block.empty() && !_is_eof && status.ok());
    }
}

```
VExchangeNode::open 会阻塞在 
```cpp
Status VDataStreamRecvr::SenderQueue::get_batch(Block* block, bool* eos) {
    std::unique_lock<std::mutex> l(_lock);
    // wait until something shows up or we know we're done
    while (!_is_cancelled && _block_queue.empty() && _num_remaining_senders > 0) {
        VLOG_ROW << "wait arrival fragment_instance_id=" << _recvr->fragment_instance_id()
                 << " node=" << _recvr->dest_node_id();
        // Don't count time spent waiting on the sender as active time.
        CANCEL_SAFE_SCOPED_TIMER(_recvr->_data_arrival_timer, &_is_cancelled);
        CANCEL_SAFE_SCOPED_TIMER(
                _received_first_batch ? nullptr : _recvr->_first_batch_wait_total_timer,
                &_is_cancelled);
        _data_arrival_cv.wait(l);
    }
    return _inner_get_batch_without_lock(block, eos);
}
```

### pipeline
```cpp
Status VExchangeNode::alloc_resource(RuntimeState* state) {
    RETURN_IF_ERROR(ExecNode::alloc_resource(state));
    if (_is_merging) {
        RETURN_IF_ERROR(_vsort_exec_exprs.open(state));
        if (!state->enable_pipeline_exec()) {
            RETURN_IF_ERROR(_stream_recvr->create_merger(_vsort_exec_exprs.lhs_ordering_expr_ctxs(),
                                                         _is_asc_order, _nulls_first,
                                                         state->batch_size(), _limit, _offset));
        }
    }
    return Status::OK();
}
```
pipe-line 的时候，执行 VExchangeNode::alloc_resource 不会阻塞，阻塞过程被转移到了 
```cpp
Status VExchangeNode::get_next(RuntimeState* state, Block* block, bool* eos) {
    SCOPED_TIMER(runtime_profile()->total_time_counter());
    if (_is_merging && state->enable_pipeline_exec() && !_is_ready) {
        RETURN_IF_ERROR(_stream_recvr->create_merger(_vsort_exec_exprs.lhs_ordering_expr_ctxs(),
                                                     _is_asc_order, _nulls_first,
                                                     state->batch_size(), _limit, _offset));
        _is_ready = true;
        return Status::OK();
    }
    auto status = _stream_recvr->get_next(block, eos);
    ...
}
```
当 SenderQueue::cancel 被调用时，阻塞行为结束
```cpp
void VDataStreamRecvr::SenderQueue::cancel(Status cancel_status) {
    {
        std::lock_guard<std::mutex> l(_lock);
        if (_is_cancelled) {
            return;
        }
        _is_cancelled = true;
        _cancel_status = cancel_status;
        if (_dependency) {
            _dependency->set_always_done();
        }
        VLOG_QUERY << "cancelled stream: _fragment_instance_id="
                   << print_id(_recvr->fragment_instance_id())
                   << " node_id=" << _recvr->dest_node_id();
    }
    // Wake up all threads waiting to produce/consume batches.  They will all
    // notice that the stream is cancelled and handle it.
    _data_arrival_cv.notify_all();
    // _data_removal_cv.notify_all();
    // PeriodicCounterUpdater::StopTimeSeriesCounter(
    //         _recvr->_bytes_received_time_series_counter);

    {
        std::lock_guard<std::mutex> l(_lock);
        for (auto closure_pair : _pending_closures) {
            closure_pair.first->Run();
        }
        _pending_closures.clear();
    }
}

void VDataStreamRecvr::cancel_stream(Status exec_status) {
    VLOG_QUERY << "cancel_stream: fragment_instance_id=" << print_id(_fragment_instance_id)
               << exec_status;

    for (int i = 0; i < _sender_queues.size(); ++i) {
        _sender_queues[i]->cancel(exec_status);
    }
}

void VDataStreamMgr::cancel(const TUniqueId& fragment_instance_id, Status exec_status) {
    VLOG_QUERY << "cancelling all streams for fragment=" << fragment_instance_id;
    std::vector<std::shared_ptr<VDataStreamRecvr>> recvrs;
    {
        std::lock_guard<std::mutex> l(_lock);
        FragmentStreamSet::iterator i =
                _fragment_stream_set.lower_bound(std::make_pair(fragment_instance_id, 0));
        while (i != _fragment_stream_set.end() && i->first == fragment_instance_id) {
            std::shared_ptr<VDataStreamRecvr> recvr = find_recvr(i->first, i->second, false);
            if (recvr == nullptr) {
                // keep going but at least log it
                std::stringstream err;
                err << "cancel(): missing in stream_map: fragment=" << i->first
                    << " node=" << i->second;
                LOG(ERROR) << err.str();
            } else {
                recvrs.push_back(recvr);
            }
            ++i;
        }
    }

    // cancel_stream maybe take a long time, so we handle it out of lock.
    for (auto& it : recvrs) {
        it->cancel_stream(exec_status);
    }
}
```
```cpp

void TaskScheduler::_do_work(size_t index) {
    ...
    while (*marker) {
        auto* task = _task_queue->take(index);
        ...
        bool canceled = fragment_ctx->is_canceled();
        if (canceled) {
            Status cancel_status = fragment_ctx->get_query_context()->exec_status();
            _try_close_task(task, PipelineTaskState::CANCELED, cancel_status);
            continue;
        }
        ...
        try {
            status = task->execute(&eos);
        } catch (const Exception& e) {
            status = e.to_status();
        }
        if (!status.ok()) {
            task->set_eos_time();
            fragment_ctx->cancel(PPlanFragmentCancelReason::INTERNAL_ERROR, status.to_string());
            _try_close_task(task, PipelineTaskState::CANCELED, status);
            continue;
        }
    }
}
```
pipeline engine 当某个 stask 失败后，会调用 `PipelineFragmentContext::cancel`
```cpp
void PipelineFragmentContext::cancel(const PPlanFragmentCancelReason& reason,
                                     const std::string& msg) {
    ...
    if (_query_ctx->cancel(true, msg, Status::Cancelled(msg))) {
        ...
        _runtime_state->set_process_status(_query_ctx->exec_status());
        // Get pipe from new load stream manager and send cancel to it or the fragment may hang to wait read from pipe
        // For stream load the fragment's query_id == load id, it is set in FE.
        auto stream_load_ctx = _exec_env->new_load_stream_mgr()->get(_query_id);
        if (stream_load_ctx != nullptr) {
            stream_load_ctx->pipe->cancel(msg);
        }
        ...
        _exec_env->vstream_mgr()->cancel(_fragment_instance_id, Status::Cancelled(msg));
        ...
    }
}
```
在该函数中 cancel 当前 be 上的这个 query
```cpp

```
```cpp

Status PipelineFragmentContext::_build_pipeline_tasks
    RETURN_IF_ERROR(pipeline->build_operators())
    {
        Status Pipeline::build_operators() {
        OperatorPtr pre;
        for (auto& operator_t : _operator_builders) {
            auto o = operator_t->build_operator();
            if (pre) {
                static_cast<void>(o->set_child(pre));
            }
            _operators.emplace_back(o);
            pre = std::move(o);
        }
        return Status::OK();
}
}

exchange_source_operator.cpp:33
```


=====================

```txt {.line-numbers}
mysql [test]>explain select id, reverse(c_array1) from array_test2 order by id;
--------------
explain select id, reverse(c_array1) from array_test2 order by id
--------------

+-------------------------------------------------------------------------------+
| Explain String(Nereids Planner)                                               |
+-------------------------------------------------------------------------------+
| PLAN FRAGMENT 0                                                               |
|   OUTPUT EXPRS:                                                               |
|     id[#5]                                                                    |
|     reverse(c_array1)[#6]                                                     |
|   PARTITION: UNPARTITIONED                                                    |
|                                                                               |
|   HAS_COLO_PLAN_NODE: false                                                   |
|                                                                               |
|   VRESULT SINK                                                                |
|      MYSQL_PROTOCAL                                                           |
|                                                                               |
|   136:VMERGING-EXCHANGE                                                       |
|      offset: 0                                                                |
|                                                                               |
| PLAN FRAGMENT 1                                                               |
|                                                                               |
|   PARTITION: HASH_PARTITIONED: id[#0]                                         |
|                                                                               |
|   HAS_COLO_PLAN_NODE: false                                                   |
|                                                                               |
|   STREAM DATA SINK                                                            |
|     EXCHANGE ID: 136                                                          |
|     UNPARTITIONED                                                             |
|                                                                               |
|   133:VSORT                                                                   |
|   |  order by: id[#5] ASC                                                     |
|   |  offset: 0                                                                |
|   |                                                                           |
|   127:VOlapScanNode                                                           |
|      TABLE: default_cluster:test.array_test2(array_test2), PREAGGREGATION: ON |
|      partitions=1/1, tablets=1/1, tabletList=19062                            |
|      cardinality=7, avgRowSize=1143.5714, numNodes=1                          |
|      pushAggOp=NONE                                                           |
|      projections: id[#0], reverse(c_array1[#1])                               |
|      project output tuple id: 1                                               |
+-------------------------------------------------------------------------------+
```
研究下 reverse 这个函数是怎么被执行的。上面这个 plan 中一共出现了两个 reverse，其中第 12 行的 reverse 函数后面有个#，代表这只是一个别名，第 42 行的 reverse 表示该函数是在 FRAGMENT 1 的 VOlapScanNode 中被执行的，它属于 projections 操作的一部分，即 VOLAPScanNode 在进行 projection 的时候需要执行 reverse 函数。

执行过程：
```cpp {.line-numbers}
Status ExecNode::get_next_after_projects(
        RuntimeState* state, vectorized::Block* block, bool* eos,
        const std::function<Status(RuntimeState*, vectorized::Block*, bool*)>& func,
        bool clear_data) {
    if (_output_row_descriptor) {
        if (clear_data) {
            clear_origin_block();
        }
        auto status = func(state, &_origin_block, eos);
        if (UNLIKELY(!status.ok())) return status;
        return do_projections(&_origin_block, block);
    }
    _peak_memory_usage_counter->set(_mem_tracker->peak_consumption());
    return func(state, block, eos);
}

Status ExecNode::do_projections(vectorized::Block* origin_block, vectorized::Block* output_block) {
    SCOPED_TIMER(_projection_timer);
    using namespace vectorized;
    MutableBlock mutable_block =
            VectorizedUtils::build_mutable_mem_reuse_block(output_block, *_output_row_descriptor);
    auto rows = origin_block->rows();

    if (rows != 0) {
        auto& mutable_columns = mutable_block.mutable_columns();
        for (int i = 0; i < mutable_columns.size(); ++i) {
            auto result_column_id = -1;
            RETURN_IF_ERROR(_projections[i]->execute(origin_block, &result_column_id));
            ...
        } else {
            mutable_columns[i]->insert_range_from(*column_ptr, 0, rows);
        }
    }

    return Status::OK();
}

Status VExprContext::execute(vectorized::Block* block, int* result_column_id) {
    Status st;
    RETURN_IF_CATCH_EXCEPTION({
        st = _root->execute(this, block, result_column_id);
        _last_result_column_id = *result_column_id;
    });
    return st;
}
```
初始化过程：
```cpp {.line-numbers}
Status ExecNode::init(const TPlanNode& tnode, RuntimeState* state) {
    init_runtime_profile(get_name());

    if (tnode.__isset.vconjunct) {
        vectorized::VExprContextSPtr context;
        RETURN_IF_ERROR(vectorized::VExpr::create_expr_tree(tnode.vconjunct, context));
        _conjuncts.emplace_back(context);
    } else if (tnode.__isset.conjuncts) {
        for (auto& conjunct : tnode.conjuncts) {
            vectorized::VExprContextSPtr context;
            RETURN_IF_ERROR(vectorized::VExpr::create_expr_tree(conjunct, context));
            _conjuncts.emplace_back(context);
        }
    }

    // create the projections expr
    if (tnode.__isset.projections) {
        DCHECK(tnode.__isset.output_tuple_id);
        RETURN_IF_ERROR(vectorized::VExpr::create_expr_trees(tnode.projections, _projections));
    }

    return Status::OK();
}
```
每个类型的 node 在执行其重载的 init 函数时几乎都会调用 ExecNode::init 函数，该函数会初始化得到的

```cpp {.line-numbers}
Status VExpr::create_expr_trees(const std::vector<TExpr>& texprs, VExprContextSPtrs& ctxs) {
    ctxs.clear();
    for (int i = 0; i < texprs.size(); ++i) {
        VExprContextSPtr ctx;
        RETURN_IF_ERROR(create_expr_tree(texprs[i], ctx));
        ctxs.push_back(ctx);
    }
    return Status::OK();
}

Status VExpr::create_expr_tree(const TExpr& texpr, VExprContextSPtr& ctx) {
    ...
    int node_idx = 0;
    VExprSPtr e;
    Status status = create_tree_from_thrift(texpr.nodes, &node_idx, e, ctx);
    ...
}

Status VExpr::create_tree_from_thrift(const std::vector<TExprNode>& nodes, int* node_idx,
                                      VExprSPtr& root_expr, VExprContextSPtr& ctx) {
    int root_children = nodes[*node_idx].num_children;
    VExprSPtr root;
    RETURN_IF_ERROR(create_expr(nodes[*node_idx], root));
    root_expr = root;
    ctx = std::make_shared<VExprContext>(root);

    // non-recursive traversal
    std::stack<std::pair<VExprSPtr, int>> s;
    s.push({root, root_children});
    while (!s.empty()) {
        ...
        RETURN_IF_ERROR(create_expr(nodes[*node_idx], expr));
        ...
    }
}

Status VExpr::create_expr(const TExprNode& expr_node, VExprSPtr& expr) {
    ...
    switch (expr_node.node_type) {
        ...
        case TExprNodeType::ARITHMETIC_EXPR:
        case TExprNodeType::BINARY_PRED:
        case TExprNodeType::FUNCTION_CALL:
        case TExprNodeType::COMPUTE_FUNCTION_CALL: {
            expr = VectorizedFnCall::create_shared(expr_node);
            break;
        }
        ...
    }
}

```

