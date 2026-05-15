
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Runtime Filter](#runtime-filter)
  - [Principles](#principles)
  - [Doris runtime filter](#doris-runtime-filter)
    - [FE](#fe)
    - [BE](#be)
      - [RuntimeFilterConsumer](#runtimefilterconsumer)

<!-- /code_chunk_output -->


# Runtime Filter
## Principles
students
|id|name|age|
|--|--|--|
|1|A|10|
|2|B|12|
|3|C|11|
|4|D|13|
|5|E|9|

takes
|id|course|guard|
|--|--|--|
|1|Math|95|
|2|Language|91|
|3|Language|89|
|4|Painting|97|
|5|Physical|88|

`SELECT * FROM students JOIN takes ON students.id = taeks.id WHERE students.age > 10`

For above relation and query, we will have a typical query like:
```text
                  Join

    Sink 5 rows         Sink 4 rows
    Scan(takes)         Scan(students)
                            Filter(age > 10)
```
So for join build stage, we will get records like
```text
1   A   10
2   B   12
3   C   11
4   D   13
```
After we finished partition and build hash index for block from students, we will do probe stage by scanning fully data from takes table, it is 5 rows in total.

**Runtime filter aims to do filter on relation takes too.**

Look into detailes of scan result of students. **We can calculate a statistical index for the output block.** Statistical index is not a typical index like B+Tree index, statistical index includes bloom-filter index & minmix index and so on. Take minmax index as an example, we can get blow statistics for **join attributes**:
```text
min_id: 1
max_id: 4
```
If we can send such statistics to Scan node of takes, we can get a new execution plan like:
```text
                  Join
                        BuildRuntimeFilter
                        BuildStage

    Sink 4 rows         Sink 4 rows
    Scan(takes)         Scan(students)
    Filter              Filter(age > 10)
        WithMinmaxindex  
```
也就是说，我们可以减少 Probe 阶段需要的数据。原先需要 probe 5 行，现在通过 minmax index 过滤掉一行，就只需要 probe 4 行了。

这就是 Runtime Filter 的基本原理。

## Doris runtime filter
### FE
```java
protected class FragmentExecParams {
    public PlanFragment
}
```



### BE
```cpp
// vhash_join_node.cpp
Status HashJoinNode::sink(doris::RuntimeState* state, vectorized::Block* in_block, bool eos) {
    ...
    // hash table has already been built
    if (!_should_build_hash_table) {
        ...
        [&](auto&& arg) -> Status {
            if (_runtime_filter_descs.empty()) {
                return Status::OK();
            }
            _runtime_filter_slots = std::make_shared<VRuntimeFilterSlots>(
                    _build_expr_ctxs, _runtime_filter_descs);

            RETURN_IF_ERROR(_runtime_filter_slots->init(
                    state, arg.hash_table->size(), 0));
            RETURN_IF_ERROR(_runtime_filter_slots->copy_from_shared_context(
                    _shared_hash_table_context));
            RETURN_IF_ERROR(_runtime_filter_slots->publish());
            return Status::OK();}
    }
}
```

merge_filter rpc 用来传递 runtime filter。
```cpp
void PInternalServiceImpl::merge_filter(...
                                        const ::doris::PMergeFilterRequest* request,
                                        ::doris::PMergeFilterResponse* response
                                        ...)
{
    ...
    Status st = _exec_env->fragment_mgr()->merge_filter(request, &zero_copy_input_stream);
    ...
}

Status FragmentMgr::merge_filter(const PMergeFilterRequest* request,
                                 butil::IOBufAsZeroCopyInputStream* attach_data)
{
    ,,,
    std::shared_ptr<RuntimeFilterMergeControllerEntity> filter_controller;
    _runtimefilter_controller.acquire(queryid, &filter_controller);
    ...
    filter_controller->merge(request, attach_data, opt_remote_rf);
}

Status RuntimeFilterMergeControllerEntity::merge(
        const PMergeFilterRequest* request,
        butil::IOBufAsZeroCopyInputStream* attach_data,
        bool opt_remote_rf)
{

}
```
多个不同的节点发送的 runtime filter 需要在 scan node 上进行合并。

```cpp
// RuntimeFilterMergeController has a map query-id -> entity
class RuntimeFilterMergeController {
public:
    RuntimeFilterMergeController() = default;
    ~RuntimeFilterMergeController() = default;

    // thread safe
    // add a query-id -> entity
    // If a query-id -> entity already exists
    // add_entity will return a exists entity
    Status add_entity(const TExecPlanFragmentParams& params,
                      std::shared_ptr<RuntimeFilterMergeControllerEntity>* handle,
                      RuntimeState* state);
    Status add_entity(const TPipelineFragmentParams& params,
                      const TPipelineInstanceParams& local_params,
                      std::shared_ptr<RuntimeFilterMergeControllerEntity>* handle,
                      RuntimeState* state);
    // thread safe
    // increase a reference count
    // if a query-id is not exist
    // Status.not_ok will be returned and a empty ptr will returned by *handle
    Status acquire(UniqueId query_id, std::shared_ptr<RuntimeFilterMergeControllerEntity>* handle);

    // thread safe
    // remove a entity by query-id
    // remove_entity will be called automatically by entity when entity is destroyed
    Status remove_entity(UniqueId query_id);

    static const int kShardNum = 128;

private:
    uint32_t _get_controller_shard_idx(UniqueId& query_id) {
        return (uint32_t)query_id.hi % kShardNum;
    }

    std::mutex _controller_mutex[kShardNum];
    // We store the weak pointer here.
    // When the external object is destroyed, we need to clear this record
    using FilterControllerMap =
            std::unordered_map<std::string, std::weak_ptr<RuntimeFilterMergeControllerEntity>>;
    // str(query-id) -> entity
    FilterControllerMap _filter_controller_map[kShardNum];
};

```
```cpp
Status FragmentMgr::exec_plan_fragment(const TPipelineFragmentParams& params,
                                       const FinishCallback& cb)
{
    ...
    auto pre_and_submit = [&](int i) {
        ...
        std::shared_ptr<RuntimeFilterMergeControllerEntity> handler;
        static_cast<void>(_runtimefilter_controller.add_entity(
                params, local_params, &handler, context->get_runtime_state(UniqueId())));
        context->set_merge_controller_handler(handler);
    }
    ...
}

Status RuntimeFilterMergeController::add_entity(
        const TPipelineFragmentParams& params, const TPipelineInstanceParams& local_params,
        std::shared_ptr<RuntimeFilterMergeControllerEntity>* handle, RuntimeState* state) {
    if (!local_params.__isset.runtime_filter_params ||
        local_params.runtime_filter_params.rid_to_runtime_filter.size() == 0) {
        return Status::OK();
    }

    runtime_filter_merge_entity_closer entity_closer =
            std::bind(runtime_filter_merge_entity_close, this, std::placeholders::_1);

    UniqueId query_id(params.query_id);
    std::string query_id_str = query_id.to_string();
    UniqueId fragment_instance_id = UniqueId(local_params.fragment_instance_id);
    uint32_t shard = _get_controller_shard_idx(query_id);
    std::lock_guard<std::mutex> guard(_controller_mutex[shard]);
    auto iter = _filter_controller_map[shard].find(query_id_str);

    if (iter == _filter_controller_map[shard].end()) {
        *handle = std::shared_ptr<RuntimeFilterMergeControllerEntity>(
                new RuntimeFilterMergeControllerEntity(state), entity_closer);
        _filter_controller_map[shard][query_id_str] = *handle;
        const TRuntimeFilterParams& filter_params = local_params.runtime_filter_params;
        RETURN_IF_ERROR(handle->get()->init(query_id, fragment_instance_id, filter_params,
                                            params.query_options));
    } else {
        *handle = _filter_controller_map[shard][query_id_str].lock();
    }
    return Status::OK();
}
```

#### RuntimeFilterConsumer
```cpp
class VScanNode : public ExecNode, public RuntimeFilterConsumer {
    ...
    Status VScanNode::init(const TPlanNode& tnode, RuntimeState* state)
    {
        RETURN_IF_ERROR(ExecNode::init(tnode, state));
        RETURN_IF_ERROR(RuntimeFilterConsumer::init(state));
    }
    ...
    
}


class RuntimeFilterConsumer {
public:
    ...
    Status RuntimeFilterConsumer::init(RuntimeState* state) {
        _state = state;
        RETURN_IF_ERROR(_register_runtime_filter());
        return Status::OK();
    }
}


```

