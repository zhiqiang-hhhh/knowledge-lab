
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [WithoutKey & NotMerge](#withoutkey--notmerge)
  - [execute_single_add](#execute_single_add)
  - [execute_batch_add](#execute_batch_add)
- [Null 的处理](#null-的处理)
  - [WithKey](#withkey)
  - [WithoutKey](#withoutkey)

<!-- /code_chunk_output -->




`select avg(colA) from basetable` 第一阶段聚合
* WithoutKey & NotMerge

`select avg(colA) from basetable` 第二阶段聚合

* WithoutKey & DoMerge

`select colA, count(*) from basetable group by colA` 第一阶段聚合

* WithKey & NotMerge

`select colA, count(*) from basetable group by colA` 第二阶段聚合

* WithKey & DoMerge


### WithoutKey & NotMerge
```cpp {.line-numbers}
class AggSinkLocalState : public PipelineXSinkLocalState<AggSharedState> {
    ...
}

template <typename SharedState>
Status PipelineXSinkLocalState<SharedState>::init(RuntimeState* state, LocalSinkStateInfo& info) {
    ...
    _shared_state = info.shared_state->template cast<SharedState>();
    ...
}

Status AggSinkLocalState::init(RuntimeState* state, LocalSinkStateInfo& info) {
    RETURN_IF_ERROR(Base::init(state, info));
    ...
    _agg_data = Base::_shared_state->agg_data.get();
}
```
第 8 行执行的相当于是 `AggSharedState` 的默认构造函数，
```cpp
AggSharedState() {
    agg_data = std::make_unique<AggregatedDataVariants>();
    agg_arena_pool = std::make_unique<vectorized::Arena>();
}
```
#### execute_single_add
```cpp {.line-numbers}
Status AggSinkOperatorX::sink(doris::RuntimeState* state, vectorized::Block* in_block, bool eos) {
    auto& local_state = get_local_state(state);
    ...
    if (in_block->rows() > 0) {
        ...
        RETURN_IF_ERROR(local_state._executor->execute(&local_state, in_block));
    }
    ...
}

AggSinkLocalState::_execute_without_key(block) {
    for (int i = 0; i < Base::_shared_state->aggregate_evaluators.size(); ++i) {
        RETURN_IF_ERROR(Base::_shared_state->aggregate_evaluators[i]->execute_single_add(
                block,
                _agg_data->without_key + Base::_parent->template cast<AggSinkOperatorX>()
                                                 ._offsets_of_aggregate_states[i],
                _agg_arena_pool));
    }
}

Status AggFnEvaluator::execute_single_add(Block* block, AggregateDataPtr place, Arena* arena) {
    RETURN_IF_ERROR(_calc_argument_columns(block));
    _function->add_batch_single_place(block->rows(), place, _agg_columns.data(), arena);
    return Status::OK();
}

void add_batch_single_place(size_t batch_size, AggregateDataPtr place, const IColumn** columns,
                                Arena* arena) const override {
        for (size_t i = 0; i < batch_size; ++i) {
            assert_cast<const Derived*>(this)->add(place, columns, i, arena);
        }
    }
```
15 行计算当前 agg 函数的 agg data 地址。


#### execute_batch_add

```cpp
Status AggFnEvaluator::execute_batch_add(Block* block, size_t offset, AggregateDataPtr* places,
                                         Arena* arena, bool agg_many) {
    RETURN_IF_ERROR(_calc_argument_columns(block));
    _function->add_batch(block->rows(), places, offset, _agg_columns.data(), arena, agg_many);
    return Status::OK();
}
```
places 是一个指针数组，每个 value 保存着保存第 i 行 agg key 的 agg states 的"段地址"
offset 则是段地址内的偏移量，`places[i] + offest` 就是当前 agg 函数的 agg state 保存的地址。

```cpp
Status AggFnEvaluator::_calc_argument_columns(Block* block) {
    SCOPED_TIMER(_expr_timer);
    _agg_columns.resize(_input_exprs_ctxs.size());
    std::vector<int> column_ids(_input_exprs_ctxs.size());
    for (int i = 0; i < _input_exprs_ctxs.size(); ++i) {
        int column_id = -1;
        RETURN_IF_ERROR(_input_exprs_ctxs[i]->execute(block, &column_id));
        column_ids[i] = column_id;
    }
    materialize_block_inplace(*block, column_ids.data(),
                              column_ids.data() + _input_exprs_ctxs.size());
    for (int i = 0; i < _input_exprs_ctxs.size(); ++i) {
        _agg_columns[i] = block->get_by_position(column_ids[i]).column.get();
    }
    return Status::OK();
}
```
`_calc_argument_columns` 执行需要执行的标量函数，构造用于 agg 的 column。比如 
`select number, sum(number + 1) from numbers("number"="10") group by number`，这里的 `number + 1` 就是在 `_calc_argument_columns` 做的，`_agg_columns` 中保存的是表达式计算之后的结果列。这些结果列将会塞给 `sum` 这个 aggregate 函数。


`add_batch` 逐行计算调用 agg 函数的 add 方法，第一个参数指向该 agg 函数用到的 agg state，第二个参数则是当前 agg 函数的入参列。大部分 agg 函数可能只有一个如参列，有个别 agg 函数可能有多个入参，此时 `columns` 就会大小超过 1。
```cpp
/// Implement method to obtain an address of 'add' function.
template <typename Derived>
class IAggregateFunctionHelper : public IAggregateFunction {
    void add_batch(size_t batch_size, AggregateDataPtr* places, size_t place_offset,
                    const IColumn** columns, Arena* arena, bool agg_many) const override {
        for (size_t i = 0; i < batch_size; ++i) {
            assert_cast<const Derived*>(this)->add(places[i] + place_offset, columns, i, arena);
        }
    }
}
```
简单点的 agg 函数，比如 count，他的 agg state 的类型就就是一个 `UInt64`
```cpp
struct AggregateFunctionCountData {
    UInt64 count = 0;
};

/// Simply count number of calls.
class AggregateFunctionCount final
        : public IAggregateFunctionDataHelper<AggregateFunctionCountData, AggregateFunctionCount> {
public:
    void add(AggregateDataPtr __restrict place, const IColumn**, ssize_t, Arena*) const override {
        ++data(place).count;
    }
}
```
复杂点的 `percentile_approx` 则会在 agg state data 的地方构造一个 `PercentileApproxState` 对象。
```cpp
struct PercentileApproxState {
    void add(double source, double quantile) {
        digest->add(source);
        target_quantile = quantile;
    }
    ...
    bool init_flag = false;
    std::unique_ptr<TDigest> digest;
    double target_quantile = INIT_QUANTILE;
    double compressions = 10000;
}

class AggregateFunctionPercentileApprox
        : public IAggregateFunctionDataHelper<PercentileApproxState,
                                              AggregateFunctionPercentileApprox> {}

template <bool is_nullable>
class AggregateFunctionPercentileApproxTwoParams : public AggregateFunctionPercentileApprox {
    void add(AggregateDataPtr __restrict place, const IColumn** columns, ssize_t row_num,
            Arena*) const override {
        const auto& sources = assert_cast<const ColumnFloat64&>(*columns[0]);
        const auto& quantile = assert_cast<const ColumnFloat64&>(*columns[1]);

        this->data(place).init();
        this->data(place).add(sources.get_element(row_num), quantile.get_element(row_num));
    }

}
```

### Null 的处理
#### WithKey
WithKey 指的是 group by 如何处理 null。
#### WithoutKey
WithoutKey 就是 agg 函数不带 group by 时怎么处理 null。
```cpp
template <typename NestFuction, bool result_is_nullable>
class AggregateFunctionNullUnaryInline final
        : public AggregateFunctionNullBaseInline<
                  NestFuction, result_is_nullable,
                  AggregateFunctionNullUnaryInline<NestFuction, result_is_nullable>> {
public:
    AggregateFunctionNullUnaryInline(IAggregateFunction* nested_function_,
                                     const DataTypes& arguments)
            : AggregateFunctionNullBaseInline<
                      NestFuction, result_is_nullable,
                      AggregateFunctionNullUnaryInline<NestFuction, result_is_nullable>>(
                      nested_function_, arguments) {}

    void add(AggregateDataPtr __restrict place, const IColumn** columns, ssize_t row_num,
             Arena* arena) const override {
        const ColumnNullable* column = assert_cast<const ColumnNullable*>(columns[0]);
        if (!column->is_null_at(row_num)) {
            this->set_flag(place);
            const IColumn* nested_column = &column->get_nested_column();
            this->nested_function->add(this->nested_place(place), &nested_column, row_num, arena);
        }
    }
    ...
}
```

```
```
\[ \frac{1}{m_0}(m_4 - (4 * m_3 - (6 * m_2 - \frac{3 * m_1^2}{m_0} ) \frac{m_1}{m_0})\frac{m_1}{m_0})\]

/// \[ \frac{1}{m_0} (m_3 - (3 * m_2 - \frac{2 * {m_1}^2}{m_0}) * \frac{m_1}{m_0});\]