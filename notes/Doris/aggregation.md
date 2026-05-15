
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Aggregate](#aggregate)
  - [DistinctStreamingAggOperatorX](#distinctstreamingaggoperatorx)
  - [AggSinkOperatorX & AggSourceOperatorX](#aggsinkoperatorx--aggsourceoperatorx)
  - [StreamingAggOperatorX](#streamingaggoperatorx)

<!-- /code_chunk_output -->

```plantuml
skinparam defaultFontSize 10
skinparam activityDiamondFontSize 3

struct BasicSharedState {
    + source_deps : std::vector<DependencySPtr>
    + sink_deps : std::vector<DependencySPtr>
    + id : ini
    + related_op_ids : set<int>
    + cast<TARGET>() : TARGET&
    + create_source_dependency(op_id, node_id, name) : Dependency*
    + create_sink_dependency(desc_id, node_id, name) : Dependency*

}

class PipelineXLocalStateBase {
    + cast<TARGET>() : TARGET&
    + {abstract} init(RuntimeState*, LocalStateInfo) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} close(RuntimeState*) : Status
    + {abstract} dependencies() : std::vector<Dependency*>
    + conjuncts() : VExprContextSPtrs
    + projections() : VExprContextSPtrs
}

class PipelineXLocalState<SharedStateArg> {
    - _dependency : Dependency*
    - _shared_state : SharedStateArg*
    + dependencies() : std::vector<Dependency*>
}

class AggSourceLocalState {
    - _places : PODArray<char*>
}

struct AggSharedState {
    + agg_date : AggregatedDataVariants
    + aggregate_data_container : AggregateDataContainer
    + agg_arena_pool : Arena 
    - aggregate_evaluators : vector<AggFnEvaluator*>
}

struct AggregatedDataVariants {
    + _type : HashKeyType
    + init(Type) : void
}

struct DataVariants <MethodsVariants> {
    + method_variant : MethodsVariants
}

class AggSinkLocalState {
    - _agg_data : AggregatedDataVariants*
    - _agg_arena_pool : Arena*
    - _executor : Executor<WithOutKey, MeedToMerge>
}

class PipelineXSinkLocalState <SharedStateArg> {
    - _shared_state : SharedStateArg*
}

class PipelineXSinkLocalStateBase {
    + {abstract} init(RuntimeState*, LocalStateInfo) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} close(RuntimeState*) : Status
}

class DataSinkOperatorXBase {
    + {abstract} init(TPlanNode&, RuntimeState*) : Status
    + {abstract} sink(RuntimeState*, Block*, bool eos) : Status
}

class DataSinkOperatorX <LocalStateType> {

}

class AggSinkOperatorX {
    - _aggregate_evaluators : vector<AggFnEvaluator*>
    - _needs_finalize : bool
    - _is_merge : bool
    _is_first_phase : bool
}

class AggFnEvaluator  {
    - _function : AggregateFunctionPtr
    + execute_single_add(Block*, AggregateData*, Arena*) : Status
    ... a lot of agg functions
}

interface IAggregateFunction {
    + {abstract} add(AggregateDataPtr __restrict place, const IColumn** columns, ssize_t row_num,
                     Arena* arena) : void 
    + {abstract} add_many(AggregateDataPtr __restrict place, const IColumn** columns,
                          std::vector<int>& rows, Arena* arena) const : void

    /// Merges state (on which place points to) with other state of current aggregation function.
    + {abstract} merge(AggregateDataPtr __restrict place, ConstAggregateDataPtr rhs,
                       Arena* arena) const : void

    + {abstract} merge_vec(const AggregateDataPtr* places, size_t offset, ConstAggregateDataPtr rhs,
                           Arena* arena, const size_t num_rows) const : void

}

class StreamingAggLocalState {
    - _agg_data : AggregatedDataVariants
    - _aggregate_data_container : AggregateDataContainer
}

interface StatefulOperatorX<LocalStateType> {
    + get_block(RuntimeState*, Block* block, bool* eos) : Status
    + {abstract} pull(RuntimeState*, Block* block, bool eos) : Status
    + {abstract} push(RuntimeState*, Block*, bool eos) : Status
    + {abstract} need_more_input_data(RuntimeState*) : bool
}

class StreamingAggOperatorX {
    - _aggregate_evaluators : vector<vectorized::AggFnEvaluator*> 
}

interface DataSinkOperatorXBase {

}

interface OperatorX <LocalStateType> {
    + {abstract} get_block(RuntimeState*, Block* block, bool* eos) : Status
}

interface OperatorXBase {
    - _projections
    - _conjuncts
    - _node_id
    - _operator_id
}

interface OperatorBase {
    + {abstract} is_sink() : bool
    + {abstract} is_source() : bool
    + {abstract} init(TDataSink&) : Status
    + {abstract} prepare(RuntimeState*) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} close(RuntimeState*) : Status
    - _child_x : OperatorXBase
}

class PipelineTask {
    - _blocked_dep : Dependency*
    - _execution_dep : Dependency*
    - _sink_shared_state : BasicSharedState
    - _op_shared_states : map<operator_id, BasicSharedState>
    - _operators : vector<OperatorX> ; // left is _source, right is _root
    - _source : OperatorXBase
    - _root : OperatorXBase
    - _sink : DataSinkOperatorX
}

class Dependency {
    is_blocked_by(PipelineTask*) : Dependency*
}


struct MethodBaseInner <HashMap> {
    + hash_values : std::vector<size_t>
    + bucket_nums : std::vector<uint32_t>
    + {abstract} init_serialized_keys(ColumnRawPtrs, size_t num_rows, null_map, is_join, is_build, bucket_size) : void
    + hash_table : HashMapPtr
    + lazy_emplace(State& state, size_t i, F&& creator, FF&& creator_for_null_key) : value
    + lazy_emplace_without_prefetch(State&, size_t i, F&& creator, FF&& creator_for_null_key) : value
}

class HashMethodBase <typename Derived, typename Value, typename Mapped> {
    + lazy_emplace_key(Data& data, size_t row, KeyHolder&& key)
    + find_key_with_hash
}

class HashMethodSerialized<typename Value, typename Mapped> {

}

struct MethodBase <HashMap> {

}

struct MethodOneNumber <typename FieldType, typename TData> {
    + init_serialized_keys(...) : void
    + using Base=ColumnsHashing::HashMethodOneNumber<TData>
}

struct MethodSerialized <TData> {
    + build_stored_keys : vector<StringRef>
    + build_arena : Arena
    + stored_keys : vector<StringRef>
}

class StreamingAggLocalState {
    - _agg_data : AggregatedDataVariants
}

AggFnEvaluator *-- IAggregateFunction
AggSharedState -up-> BasicSharedState
AggSharedState *-right- DataVariants : DataVariants<AggregatedDataVariants>
AggSharedState *-- AggFnEvaluator
AggSinkLocalState -up-> PipelineXSinkLocalState : PipelineXSinkLocalState<AggSharedState>
AggSinkOperatorX -up-> DataSinkOperatorX : DataSinkOperatorXBase<AggSinkLocalState>
AggSourceLocalState -up-> PipelineXLocalState : PipelineXLocalState<AggSharedState>
AggSourceOperatorX -up-> OperatorX : OperatorX<AggSourceLocalState>
AggregatedDataVariants --> DataVariants : DataVariants<AggregatedMethodVariants>

BasicSharedState *-- Dependency

DataVariants *-- MethodBaseInner
DataSinkOperatorX -up-> DataSinkOperatorXBase
DataSinkOperatorX *-- PipelineXSinkLocalStateBase
DataSinkOperatorXBase -up-> OperatorBase

HashMethodSerialized --> HashMethodBase : HashMethodBase<HashMethodSerialized<Value, Mapped>, Value, Mappped>
HashMethodOneNumber --> HashMethodBase : HashMethodBase<HashMethodOneNumber<Value, Mapped>, Value, Mappped>

MethodBase -up-> MethodBaseInner : MethodBaseInner<HashMap>
MethodOneNumber -up-> MethodBase : MethodBase<TData>
MethodOneNumber -- HashMethodOneNumber
MethodSerialized -up-> MethodBase : MethodBase<TData>
MethodSerialized -- HashMethodSerialized

PipelineTask *-right- Dependency
PipelineTask *-right- BasicSharedState
PipelineTask *-left- OperatorX
PipelineTask *-left- DataSinkOperatorX
PipelineXLocalState -up-> PipelineXLocalStateBase
PipelineXLocalState *-- BasicSharedState
PipelineXSinkLocalState -up-> PipelineXSinkLocalStateBase
PipelineXSinkLocalState *-- BasicSharedState

StreamingAggOperatorX -up-> StatefulOperatorX : StatefulOperatorX<StreamingAggLocalState>
StreamingAggOperatorX *-- AggFnEvaluator
StreamingAggLocalState --> PipelineXLocalState : PipelineXLocalState<FakeSharedState>
StreamingAggLocalState *-left- DataVariants : DataVariants<AggregatedDataVariants>
StatefulOperatorX -up-> OperatorX : OperatorX<LocalStateType>

OperatorX -up-> OperatorXBase
OperatorX *-- PipelineXLocalState
OperatorXBase -up-> OperatorBase
```
### Aggregate
```cpp
case TPlanNodeType::AGGREGATION_NODE: {
    if (tnode.agg_node.aggregate_functions.empty() && !_runtime_state->enable_agg_spill() &&
            !tnode.agg_node.grouping_exprs.empty() &&
            !tnode.agg_node.__isset.agg_sort_info_by_group_key)
    {
        op.reset(new DistinctStreamingAggOperatorX(pool, next_operator_id(), tnode, descs,
                                                       _require_bucket_distribution));
        RETURN_IF_ERROR(cur_pipe->add_operator(op));
    } else if (tnode.agg_node.use_streaming_preaggregation &&
                   !tnode.agg_node.grouping_exprs.empty()) {
        op.reset(new StreamingAggOperatorX(pool, next_operator_id(), tnode, descs));
        RETURN_IF_ERROR(cur_pipe->add_operator(op));
    } else {
        if (_runtime_state->enable_agg_spill() && !tnode.agg_node.grouping_exprs.empty()) {
            op.reset(new PartitionedAggSourceOperatorX(pool, tnode, next_operator_id(), descs));
        } else {
            op.reset(new AggSourceOperatorX(pool, tnode, next_operator_id(), descs));
        }
        // pipeline breaker, create a child pipeline
        RETURN_IF_ERROR(cur_pipe->add_operator(op));
        ...
        DataSinkOperatorXPtr sink;
        if (need_partitioned_agg_source_operator) {
            sink.reset(new PartitionedAggSinkOperatorX(pool, next_sink_operator_id(), tnode,
                                                        descs, _require_bucket_distribution));
        } else {
            sink.reset(new AggSinkOperatorX(pool, next_sink_operator_id(), tnode, descs,
                                            _require_bucket_distribution));
        }
    }
}
```
各种 AggOperator 的创建规则如下：
1. 如果当前的 agg node 没有聚合函数需要执行，并且 group by 的 key 不为空，那么就创建一个 `DistinctStreamingAggOperatorX`，这个 Operator 实际上是对输入 block 进行去重，对应 sql 中的 distinct 关键字。
2. 否则如果当前 node 有 group by key，并且要求使用 streaming pre aggragation，那么就创建一个 `StreamingAggOperatorX`。 `StreamingAggOperatorX` 
3. 否则，如果允许 agg spill，并且 group by key 不为空，那么就创建一个 PartitionedAggSourceOperatorX
4. 否则，创建一个 AggSourceOperatorX

`PartitionedAggSourceOperatorX`与`AggSourceOperatorX`都是 pipeline breaker，这两个算子都要求拿到所有数据后，进行下一步操作，无法流式处理 block，所以遇到这两个算子后需要增加一条 pipeline。

```sql
select count(distinct number) from numbers("number" = "100");
```
```text
+----------------------------------------------------------+
| Explain String(Nereids Planner)                          |
+----------------------------------------------------------+
| PLAN FRAGMENT 0                                          |
|   OUTPUT EXPRS:                                          |
|     count(number)[#4]                                    |
|   PARTITION: UNPARTITIONED                               |
|                                                          |
|   VRESULT SINK                                           |
|      MYSQL_PROTOCAL                                      |
|                                                          |
|   6:VAGGREGATE (merge finalize)(167)                     |
|   |  output: count(partial_count(number)[#3])[#4]        |
|   |  group by:                                           |
|   |  distribute expr lists:                              |
|   |                                                      |
|   5:VEXCHANGE                                            |
|      offset: 0                                           |
|                                                          |
| PLAN FRAGMENT 1                                          |
|                                                          |
|   PARTITION: HASH_PARTITIONED: number[#1]                |
|                                                          |
|   STREAM DATA SINK                                       |
|     EXCHANGE ID: 05                                      |
|     UNPARTITIONED                                        |
|                                                          |
|   4:VAGGREGATE (update serialize)(161)                   |
|   |  output: partial_count(number[#2])[#3]               |
|   |  group by:                                           |
|   |  distribute expr lists: number[#2]                   |
|   |                                                      |
|   3:VAGGREGATE (merge serialize)(158)                    |
|   |  group by: number[#1]                                |
|   |  distribute expr lists: number[#1]                   |
|   |                                                      |
|   2:VEXCHANGE                                            |
|      offset: 0                                           |
|                                                          |
| PLAN FRAGMENT 2                                          |
|                                                          |
|   PARTITION: RANDOM                                      |
|                                                          |
|   STREAM DATA SINK                                       |
|     EXCHANGE ID: 02                                      |
|     HASH_PARTITIONED: number[#1]                         |
|                                                          |
|   1:VAGGREGATE (update serialize)(152)                   |
|   |  STREAMING                                           |
|   |  group by: _table_valued_function_numbers.number[#0] |
|   |                                                      |
|   0:VDataGenScanNode(149)                                |
|      table value function: NUMBERS                       |
+----------------------------------------------------------+
63 rows in set (0.02 sec)
```

```text
PLAN FRAGMENT 0

fragment = TPlanFragment {
    plan = TPlan {
        nodes = {
            [0] = TPlanNode {
                node_id = 6,
                node_type = AGGREGATION_NODE,
                agg_node = TAggregationNode {
                    aggregate_functions = list {
                        [0] = TExpr {
                            nodes = list {
                                [0] = TExprNode {
                                    node_type = AGG_EXPR,
                                    agg_expr = TAggregateExpr {
                                        is_merge_add = true,
                                    },
                                    fn = TFunction {
                                        name = count,
                                        signature = "count(BIGINT)",
                                        aggregate_fn = TAggregateFunction {
                                            ...
                                        }}},
                                [1] = TExprNode {
                                    node_type = SLOT_REF,
                                },}}}}},}}}

PLAN FRAGMENT 1

fragment = TPlanFragment {
    plan = TPlan {
        nodes = {
            [0] = TPlanNode {
                node_id = 4,
                node_type = AGGREGATION_NODE
                num_children = 1,
                agg_node = TAggregationNode {
                    aggregate_functions = {
                        [0] = TExpr {
                            nodes = list {
                                [0] = TExprNode {
                                    node_type = AGG_EXPR,
                                    num_children = 1,
                                    agg_expr = TAggregateExpr {
                                        is_merge_agg = false,
                                    },
                                    fn = TFunction {
                                        name = count
                                        signature = "count(BIGINT)",
                                        aggregate_fn = TAggregateFunction {
                                            ...
                                        }}},
                                [1] = TExprNode {
                                    node_type = SLOT_REF,
                                    slot_ref = TSlotRef {
                                        slot_id = 2,
                                        }}}},}},
            [1] = TPlanNode {
                node_id = 3,
                node_type = AGGREGATION_NODE = 6,
                num_children = 1,
                grouping_exprs = list {
                    [0] = TExpr {
                        nodes = list {
                            [0] = TExprNode {
                                node_type = SLOT_REF,
                                slot_ref = TSlotRef {
                                    slot_id = 1,
                                    }}}}},}}}}}

PLAN FRAGMENT 2

fragment = TPlanFragment {
    plan = TPlan {
        nodes = {
            [0] = TPlanNode {
                node_id = 1,
                node_type = AGGREGATION_NODE = 6,
                num_children = 1,
                agg_node = TAggregationNode {
                    grouping_exprs = {
                        [0] = TExpr {
                            nodes = {
                                [0] = TExprNode {
                                    node_type = SLOT_REF = 16,
                                    slot_ref = TSlotRef {
                                        slot_id = 0,
                                    }}}}},
                    use_streaming_preaggregation = true,
                    }},}}}
```
从 F2 开始看，这里将会对应一个 `DistinctStreamingAggOperatorX`，F1 的 PlanNode[1] 似乎跟 F0 的 distinct 重复了。。PlanNode[0] 有一个 agg 函数`count`，但是没有 group by 表达式，所以是一个 `AggSourceOperatorX`，对应还会有一个 `AggSinkOperatorX`，F0 同样有一个 `AggSourceOperatorX` 和一个 `AggSinkOperatorX`。

这个 Plan 似乎是有问题的，这里的中间的 agg node 似乎多余了。

#### DistinctStreamingAggOperatorX
`DistinctStreamingAggOperatorX` 继承自 `StatefulOperatorX`，
```cpp
template <typename LocalStateType>
Status StatefulOperatorX<LocalStateType>::get_block(RuntimeState* state, vectorized::Block* block,
                                                    bool* eos) {
    auto& local_state = get_local_state(state);
    // 如果当前 Operator 还需要更多数据
    if (need_more_input_data(state)) {
        local_state._child_block->clear_column_data(
                OperatorX<LocalStateType>::_child_x->row_desc().num_materialized_slots());

        // 从 child operator get 一个新的 block，把结果塞到当前 operator 的 local_state 的 _child_block 里
        RETURN_IF_ERROR(OperatorX<LocalStateType>::_child_x->get_block_after_projects(
                state, local_state._child_block.get(), &local_state._child_eos));
        // 如果 child operator eos，那么当前 pipeline task 也 eos
        *eos = local_state._child_eos;
        if (local_state._child_block->rows() == 0 && !local_state._child_eos) {
            return Status::OK();
        }
        {
            SCOPED_TIMER(local_state.exec_time_counter());
            // 不把 child block 返回给上层的 operator，而是由当前 operator“保留”
            RETURN_IF_ERROR(push(state, local_state._child_block.get(), local_state._child_eos));
        }
    }

    // 向上层 operator 返回 block
    if (!need_more_input_data(state)) {
        SCOPED_TIMER(local_state.exec_time_counter());
        bool new_eos = false;
        RETURN_IF_ERROR(pull(state, block, &new_eos));
        if (new_eos) {
            *eos = true;
        } else if (!need_more_input_data(state)) {
            *eos = false;
        }
    }
    return Status::OK();
}
```
`StatefulOperatorX` 并不是每输入一个 block 就一定对应输出一个 block，而是由自己控制。
对于 `DistinctStreamingAggOperatorX` 来说。每当从 child operator 拿到一个新 block，就会
1. 计算 group by 表达式的值，比如 `group by func(colA)`，这里就是计算 `func(colA)`。
2. 构建 hash 表并且去重
3. 处理 limit

其中第二步通常是整个算子中最花费时间的。第二步自身又被拆解成如下的子步骤：
1. 判断当前 hash table 大小是否超限，并且判断是否有必要继续扩展 hash 表。第二个判断条件中有一些策略，通常当前的 agg node 是预聚合阶段，并且数据源的基数占总行数比例比较大时，会提前终止 hash 表的构建。若没必要继续构建 hash 表，会设置 `DistinctStreamingAggLocalState._stop_emplace_flag` 为 true。
2. 构建 hash 表，并且构建 filter，

```cpp
Status DistinctStreamingAggOperatorX::push(RuntimeState* state, vectorized::Block* in_block,
                                           bool eos) const {
    DistinctStreamingAggLocalState& local_state = get_local_state(state);
    local_state._input_num_rows += in_block->rows();
    if (in_block->rows() == 0) {
        return Status::OK();
    }

    RETURN_IF_ERROR(local_state._distinct_pre_agg_with_serialized_key(
            in_block, local_state._aggregated_block.get()));

    // set limit and reach limit
    if (_limit != -1 &&
        (local_state._num_rows_returned + local_state._aggregated_block->rows()) > _limit) {
        auto limit_rows = _limit - local_state._num_rows_returned;
        local_state._aggregated_block->set_num_rows(limit_rows);
        local_state._reach_limit = true;
    }
    return Status::OK();
}
```

```cpp
bool DistinctStreamingAggOperatorX::need_more_input_data(RuntimeState* state) const {
    DistinctStreamingAggLocalState& local_state = get_local_state(state);
    const bool need_batch = local_state._stop_emplace_flag
                                    ? local_state._aggregated_block->empty()
                                    : local_state._aggregated_block->rows() < state->batch_size();
    return need_batch && !(local_state._child_eos || local_state._reach_limit);
}
```
```cpp
Status DistinctStreamingAggOperatorX::pull(RuntimeState* state, vectorized::Block* block,
                                           bool* eos) const {
    auto& local_state = get_local_state(state);
    if (!local_state._aggregated_block->empty()) {
        block->swap(*local_state._aggregated_block);
        local_state._aggregated_block->clear_column_data(block->columns());
        // The cache block may have additional data due to exceeding the batch size.
        if (!local_state._cache_block.empty()) {
            local_state._swap_cache_block(local_state._aggregated_block.get());
        }
    }

    local_state._make_nullable_output_key(block);
    if (!_is_streaming_preagg) {
        // dispose the having clause, should not be execute in prestreaming agg
        RETURN_IF_ERROR(
                vectorized::VExprContext::filter_block(_conjuncts, block, block->columns()));
    }
    local_state.add_num_rows_returned(block->rows());
    COUNTER_UPDATE(local_state.blocks_returned_counter(), 1);
    // If the limit is not reached, it is important to ensure that _aggregated_block is empty
    // because it may still contain data.
    // However, if the limit is reached, there is no need to output data even if some exists.
    *eos = (local_state._child_eos && local_state._aggregated_block->empty()) ||
           (local_state._reach_limit);
    return Status::OK();
}
```


#### AggSinkOperatorX & AggSourceOperatorX
```cpp
Status AggSinkOperatorX::sink(doris::RuntimeState* state, vectorized::Block* in_block, bool eos) {
    AggSinkLocalState& local_state = get_local_state(state);
    // 这里的 _shared_state 类型是 AggSharedState
    local_state._shared_state->input_num_rows += in_block->rows();
    if (in_block->rows() > 0) {
        RETURN_IF_ERROR(local_state._executor->execute(&local_state, in_block));
    }
    if (eos) {
        local_state._dependency->set_ready_to_read();
    }
    return Status::OK();
}

class AggSinkLocalState {
    AggregatedDataVariants* _agg_data = nullptr;
    vectorized::Arena* _agg_arena_pool = nullptr;
    std::unique_ptr<ExecutorBase> _executor = nullptr;

    ...

    template <bool WithoutKey, bool NeedToMerge>
    struct Executor final : public ExecutorBase {
        Status execute(AggSinkLocalState* local_state, vectorized::Block* block) override {
            if constexpr (WithoutKey) {
                if constexpr (NeedToMerge) {
                    return local_state->_merge_without_key(block);
                } else {
                    return local_state->_execute_without_key(block);
                }
            } else {
                if constexpr (NeedToMerge) {
                    return local_state->_merge_with_serialized_key(block);
                } else {
                    return local_state->_execute_with_serialized_key(block);
                }
            }
        }
    }
}
```
`AggSinkLocalState` 的 executor 是在 `AggSinkLocalState::open()` 中构造的。如果是 probe 阶段，那么 WithoutKey == true，否则为 false。
```cpp
// build 阶段执行的是：
Status AggSinkLocalState::_execute_without_key(vectorized::Block* block) {
    for (int i = 0; i < Base::_shared_state->aggregate_evaluators.size(); ++i) {
        RETURN_IF_ERROR(Base::_shared_state->aggregate_evaluators[i]->execute_single_add(
                block,
                _agg_data->without_key + Base::_parent->template cast<AggSinkOperatorX>()
                                                 ._offsets_of_aggregate_states[i],
                _agg_arena_pool));
    }
    return Status::OK();
}

Status AggFnEvaluator::execute_single_add(Block* block, AggregateDataPtr place, Arena* arena) {
    RETURN_IF_ERROR(_calc_argument_columns(block));
    _function->add_batch_single_place(block->rows(), place, _agg_columns.data(), arena);
    return Status::OK();
}

```




```cpp
AggregatedDataVariants : DataVariants<AggregatedMethodVariants>{
    template <bool nullable>
    void init(Type type) {
        case Type::int32_key:
            emplace_single<vectorized::UInt32, AggregatedDataWithUInt32Key, nullable>();
            break;
    }
}

template <typename MethodVariants, template <typename> typename MethodNullable,
          template <typename, typename> typename MethodOneNumber,
          template <typename, bool> typename MethodFixed, template <typename> typename DataNullable>
struct DataVariants {
    MethodVariants method_variant;

    template <typename T, typename TT, bool nullable>
    void emplace_single() {
        if (nullable) {
            method_variant.template emplace<MethodNullable<MethodOneNumber<T, DataNullable<TT>>>>();
        } else {
            method_variant.template emplace<MethodOneNumber<T, TT>>();
        }
    }
}

using AggregatedMethodVariants = std::variant<
    std::monostate, vectorized::MethodSerialized<AggregatedDataWithStringKey>,...>
```
这里的情况下，最后 `method_variant` 的类型应该是 `vectorized::MethodOneNumber<vectorized::UInt8, AggregatedDataWithUInt8Key>,`

#### StreamingAggOperatorX
`StreamingAggOperatorX` 与 `DistinctStreamingAggOperatorX` 一样都继承自 `StatefulOperatorX`。

```cpp
Status StreamingAggOperatorX::push(RuntimeState* state, vectorized::Block* in_block,
                                   bool eos) const {
    auto& local_state = get_local_state(state);
    local_state._input_num_rows += in_block->rows();
    if (in_block->rows() > 0) {
        RETURN_IF_ERROR(local_state.do_pre_agg(in_block, local_state._pre_aggregated_block.get()));
    }
    in_block->clear_column_data(_child_x->row_desc().num_materialized_slots());
    return Status::OK();
}
```


------
```cpp
void DistinctStreamingAggLocalState::_emplace_into_hash_table_to_distinct(
        vectorized::IColumn::Selector& distinct_row, vectorized::ColumnRawPtrs& key_columns,
        const size_t num_rows) {
    std::visit(
            vectorized::Overload {
                    [&](std::monostate& arg) -> void {
                        throw doris::Exception(ErrorCode::INTERNAL_ERROR, "uninited hash table");
                    },
                    [&](auto& agg_method) -> void {
                        SCOPED_TIMER(_hash_table_compute_timer);
                        using HashMethodType = std::decay_t<decltype(agg_method)>;
                        using AggState = typename HashMethodType::State;
                        auto& hash_tbl = *agg_method.hash_table;
                        if (_parent->cast<DistinctStreamingAggOperatorX>()._is_streaming_preagg &&
                            hash_tbl.add_elem_size_overflow(num_rows)) {
                            if (!_should_expand_preagg_hash_tables()) {
                                _stop_emplace_flag = true;
                                return;
                            }
                        }
                        AggState state(key_columns);
                        agg_method.init_serialized_keys(key_columns, num_rows);
                        size_t row = 0;
                        auto creator = [&](const auto& ctor, auto& key, auto& origin) {
                            HashMethodType::try_presis_key(key, origin, _arena);
                            ctor(key, dummy_mapped_data.get());
                            distinct_row.push_back(row);
                        };
                        auto creator_for_null_key = [&](auto& mapped) {
                            mapped = dummy_mapped_data.get();
                            distinct_row.push_back(row);
                        };

                        SCOPED_TIMER(_hash_table_emplace_timer);
                        for (; row < num_rows; ++row) {
                            agg_method.lazy_emplace(state, row, creator, creator_for_null_key);
                        }

                        COUNTER_UPDATE(_hash_table_input_counter, num_rows);
                    }},
            _agg_data->method_variant);
}

using vectorized::MethodOneNumber<vectorized::UInt8, AggregatedDataWithUInt8Key>

/// For the case where there is one numeric key.
/// FieldType is UInt8/16/32/64 for any type with corresponding bit width.
template <typename FieldType, typename TData>
struct MethodOneNumber : public MethodBase<TData> {
    
}

template <bool read>
    void ALWAYS_INLINE prefetch(const Key& key, size_t hash_value) {
        _hash_map.prefetch_hash(hash_value);
    }
```



-----
DataVariants

```plantuml
struct MethodBaseInner <HashMap> {
    + hash_values : std::vector<size_t>
    + bucket_nums : std::vector<uint32_t>
    + {abstract} init_serialized_keys(ColumnRawPtrs, size_t num_rows, null_map, is_join, is_build, bucket_size) : void
    + hash_table : HashMapPtr
    + lazy_emplace(State& state, size_t i, F&& creator, FF&& creator_for_null_key) : value
    + lazy_emplace_without_prefetch(State&, size_t i, F&& creator, FF&& creator_for_null_key) : value
}

class HashMethodBase <typename Derived, typename Value, typename Mapped> {
    + lazy_emplace_key(Data& data, size_t row, KeyHolder&& key)
    + find_key_with_hash
}

note left of HashMethodBase::lazy_emplace_key
    这里的 Data 类型是 PHHashMap
    PHHashMap 会调用 phmap 的 lazy_emplace_with_hash
end note

class HashMethodSerialized<typename Value, typename Mapped> {

}

struct MethodBase <HashMap> {

}

struct MethodOneNumber <typename FieldType, typename TData> {
    + init_serialized_keys(...) : void
    + using Base=ColumnsHashing::HashMethodOneNumber<TData>
}

struct MethodSerialized <TData> {
    + build_stored_keys : vector<StringRef>
    + build_arena : Arena
    + stored_keys : vector<StringRef>
}

struct DataVariants <MethodVariants> {
    + method_variant : MethodVariants
}

class StreamingAggLocalState {
    - _agg_data : AggregatedDataVariants
}

StreamingAggLocalState *-left- AggregatedDataVariants
MethodBase -up-> MethodBaseInner : MethodBaseInner<HashMap>
MethodOneNumber -up-> MethodBase : MethodBase<TData>
MethodSerialized -up-> MethodBase : MethodBase<TData>
AggregatedDataVariants -up-> DataVariants : DataVariants<AggregatedMethodVariants>
AggregatedDataVariants *-- MethodBase
HashMethodSerialized --> HashMethodBase : HashMethodBase<HashMethodSerialized<Value, Mapped>, Value, Mappped>
HashMethodOneNumber --> HashMethodBase : HashMethodBase<HashMethodOneNumber<Value, Mapped>, Value, Mappped>
MethodSerialized -- HashMethodSerialized
MethodOneNumber -- HashMethodOneNumber
```

```text
MethodVariants::lazy_emplace
MethodBaseInner::lazy_emplace
ColumnsHashing::HashMethodOneNumber::lazy_emplace_key
HashMethodBase::lazy_emplace_key
PHHashMap::lazy_emplace

```