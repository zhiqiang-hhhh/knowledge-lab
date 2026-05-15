
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

  - [defaultImplementationForNulls](#defaultimplementationfornulls)
  - [defaultImplementationForConstantArguments](#defaultimplementationforconstantarguments)
- [Function](#function)
  - [AggregateFunction](#aggregatefunction)
  - [IAggregateFunctionDataHelper](#iaggregatefunctiondatahelper)

<!-- /code_chunk_output -->

### defaultImplementationForNulls
```cpp
/** Default implementation in presence of Nullable arguments or NULL constants as arguments is the following:
*  if some of arguments are NULL constants then return NULL constant,
*  if some of arguments are Nullable, then execute function as usual for columns,
*   where Nullable columns are substituted with nested columns (they have arbitrary values in rows corresponding to NULL value)
*   and wrap result in Nullable column where NULLs are in all rows where any of arguments are NULL.
*/
```

首先思考一下，如果一个 Function 处理的参数可以包含 Nullable 列，那么需要怎么做。
Nullable 列可能是：
1. NULL constants
2. NullableColumn

对于第一种情况，最可能的处理是我们直接返回 NULL constant。对于第二种情况，我们可能会先得到 NestedColumn，然后处理 NestedColumn，并且绝大多数情况下，返回值类型也会是 NullableColumn，所以我们会把结果包在 NullableColumn 中返回。
`defaultImplementationForNulls` 就是把上述了逻辑实现成一个公共函数，如果需要使用这种默认处理，那么只要在实现函数时，重载让其返回 true 即可 (默认就是 true)。

```cpp
bool useDefaultImplementationForNulls() const { return true; }
```
`defaultImplementationForNulls`
```cpp
ColumnPtr IExecutableFunction::defaultImplementationForNulls(
    const ColumnsWithTypeAndName & args, const DataTypePtr & result_type, size_t input_rows_count, bool dry_run) const
{
    /// Step 0
    if (args.empty() || !useDefaultImplementationForNulls())
        return nullptr;

    ///
    NullPresence null_presence = getNullPresense(args);

    if (null_presence.has_null_constant)
    {
        // Default implementation for nulls returns null result for null arguments,
        // so the result type must be nullable.
        if (!result_type->isNullable())
            throw Exception(
                ErrorCodes::LOGICAL_ERROR,
                "Function {} with Null argument and default implementation for Nulls "
                "is expected to return Nullable result, got {}",
                getName(),
                result_type->getName());

        return result_type->createColumnConstWithDefaultValue(input_rows_count);
    }

    if (null_presence.has_nullable)
    {
        ColumnsWithTypeAndName temporary_columns = createBlockWithNestedColumns(args);
        auto temporary_result_type = removeNullable(result_type);

        auto res = executeWithoutLowCardinalityColumns(temporary_columns, temporary_result_type, input_rows_count, dry_run);
        return wrapInNullable(res, args, result_type, input_rows_count);
    }

    return nullptr;
}
```

### defaultImplementationForConstantArguments

创建 `defaultImplementationForConstantArguments` 的目的与 `defaultImplementationForNulls` 一样，都是抽象出公共逻辑。不过 `defaultImplementationForConstantArguments` 准确说其实是对于当实际入参全为 Constant 时的优化。

假设定义了函数 Function(A, B)，其中 A 必须为 Constant，B 是 Int64。如果在运行中，B 为非 Constant，那么我们只能老老实实按行计算。但是，如果 B 实际上是套了一个 ColumnConst 的 ColumnInt64，那么我们可以只计算一次 Funciton(A, B)，然后将结果拷贝实际的行数个。

`defaultImplementationForConstantArguments` 就是将上述优化做成公共逻辑。

```cpp {.line-numbers}
ColumnPtr IExecutableFunction::defaultImplementationForConstantArguments(
    const ColumnsWithTypeAndName & args, const DataTypePtr & result_type, size_t input_rows_count, bool dry_run) const
{
    // Step 0 确保入参满足函数签名
    ColumnNumbers arguments_to_remain_constants = getArgumentsThatAreAlwaysConstant();
    /// Check that these arguments are really constant.
    ...

    // Step 1 确保满足进行优化的条件
    if (args.empty() || !useDefaultImplementationForConstants() || !allArgumentsAreConstants(args))
        return nullptr;

    // Step 2 把 input_rows_count 行的全 Const 入参转为行数为 1 的 入参
    ColumnsWithTypeAndName temporary_columns;

    for (arg : args) {
        if (arg must be ConstColumn) {
            temporary_columns.push_back(arg->cloneReseized(1));
        } else {
            nested_col = assert_cast<ColumnConstant>(arg);
            temporary_columns.push_back(nested_col);
        }
    }

    // Step 3 把结果拷贝 n 次
    return ColumnConst::create(result_column, input_rows_count);
}
```
注意，这里 ConstColumn 实际行数是 input_rows_count，所以需要复制 1 个元素后在添加到 temporary_columns 中。而 else 分支里的 ColumnConstant
```cpp
if (arg must be ConstColumn) {
    temporary_columns.push_back(arg->cloneReseized(1));
} else {
    nested_col = assert_cast<ColumnConstant>(arg);
    temporary_columns.push_back(nested_col->getDataColumnPtr());
}
```

**当函数不使用怼 Nullable 以及 Const 的默认处理时，就需要函数实现自己处理 Nullable 以及 Const 的情况**，处理可以在两个地方进行：
1. 在 getReturnType 里限制某个函数是否接受 Nullable 列或者 Const 列
2. 在 execute 里对每个 block 进行处理



## Function
函数可以分为标量函数 (Scalar function) 与聚合函数 (Aggregate Function)，前者的结果与输入是一一对应的，输入 n 行得到 n 行，比如 truncate，后者的结果与输入并不是一一对应，输入 n 行得到 1 行，比如 min/max。


### AggregateFunction
所有的聚合函数都应当继承实现 `IAggregateFunction`，该函数定义了所有聚合函数应当实现的接口。

```plantuml
class IAggregateFunction {
    {abstract} destory(AggregateDataPtr) : void
    {abstract} destroy_vec(AggregateDataPtr, num_rows) : void
    {abstract} add(AggregateDataPtr, IColumn**, row_num, Arena*) : void
    {abstract} merge(AggregateDataPtr, ConstAggregateDataPtr rhs, Arena*) : void
    ...
}

IAggregateFunctionHelper -up-> IAggregateFunction

class IAggregateFunctionHelper<Derived>

IAggregateFunctionDataHelper -up-> IAggregateFunctionHelper

class IAggregateFunctionDataHelper<DataType, Derived>

class AggregateFunctionPercentile<PercentileState, AggregateFunctionPercentile>

AggregateFunctionPercentile -up-> IAggregateFunctionDataHelper
```

为什么需要 `IAggregateFunctionHelper` 这个类？通过在编译期显式 cast 指针来消除运行时的虚函数调用开销。
```cpp
template <typename Derived>
class IAggregateFunctionHelper : public IAggregateFunction {
public:
    void add_batch(...) const override
    {
        for (size_t i = 0; i < batch_size; ++i) {
            assert_cast<const Derived*>(this)->add(places[i] + place_offset, columns, i, arena);
        }
    }
}
```
为什么需要 `IAggregateFunctionDataHelper`?

### IAggregateFunctionDataHelper
所有继承实现了 `IAggregateFunctionDataHelper` 的类，都将具有 `IAggregateFunctionDataHelper` 提供的一些便利方法，
```cpp
class AggregateFunctionPercentile final
        : public IAggregateFunctionDataHelper<PercentileState, AggregateFunctionPercentile> {
        ...
        void add(AggregateDataPtr __restrict place, const IColumn** columns, ssize_t row_num,
             Arena*) const override {
            const auto& sources = assert_cast<const ColumnVector<Int64>&>(*columns[0]);
            const auto& quantile = assert_cast<const ColumnVector<Float64>&>(*columns[1]);
            AggregateFunctionPercentile::data(place).add(sources.get_int(row_num), quantile.get_data(), 1);
        }
}
```
比如对于 `AggregateFunctionPercentile` 来说，其 add 方法将会执行到 `PercentileState::add`