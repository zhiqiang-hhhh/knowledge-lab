
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Hash Table 操作](#hash-table-操作)

<!-- /code_chunk_output -->



```sql
SELECT count(1)
FROM A
INNER JOIN[shuffle] B ON A.KPI_ID = B.KPI_ID;
```

```text
FRAGMENT 0
    RESULT SINK
    MERGE-AGG
        count(partial-count(*))
    EXCHANGE 06
FRAGMENT 1
    STREAM DATA SINK:
        to EXCHANGE 06
        HASH_PARTITION by KPI_ID
    PRE-AGG
        partial-count(*)
    HASH JOIN
        INNER JOIN on A.KPI_ID = B.KPI_ID
    EXCHANGE 01
    EXCHANGE 03
FRAGMENT 2
    STREAM DATA SINK to EXCHANGE 03
    SCAN NODE
        from A
FRAGMENT 3
    STREAM DATA SINK to EXCHANGE 01
    SCAN NODE
        from B
```
```text
FRAGMENT 0
    Pipeline 0:
        RESULT_SINK
        AGGREGATION_OPERATOR
    Pipeline 1:
        AGGREGATION_SINK_OPERATOR
        EXCHANGE_OPERATOR

FRAGMENT 1:
    Pipeline 0:
        DATA_STREAM_SINK_OPERATOR
        AGGREGATION_OPERATOR
    Pipeline 1:
        AGGREGATION_SINK_OPERATOR
        HASH_JOIN_OPERATOR
        EXCHANGE_OPERATOR 03
    Pipeline 2:
        HASH_JOIN_SINK_OPERATOR
        EXCHANGE_OPERATOR 01

FRAGMENT 2:
    DATA_STREAM_SINK_OPERATOR to EXCHANGE 03
    OLAP_SCAN_OPERATOR
        from A

FRAGMENT 3:
    DATA_STREAM_SINK_OPERATOR to EXCHANGE 01
    OLAP_SCAN_OPERATOR
        from B
```
Fragment 1 收到的 Thrift Plan 结构：
```text
fragment = TPlanFragment 
    nodes = List<TPlanNode>[4]
    [0] TPlanNode
        node_id = 5
        node_type = AGGREGATION_NODE
        num_children = 1
        agg_node = TAggregationNode {
            aggregate_functions(list) =
                [0] TExpr
                    [0] TExprNode {
                        type = 0
                        scale_type = 6
                        agg_expr {
                            is_merge_agg = false
                        }
                        fn = TFunction
                            function_name = count
                    }
    [1] TPlanNode {
        node_id = 4,
        node_type = HASH_JOIN_NODE,
        num_children = 2
        hash_join_node = THashJoinNode {
            join_op = 0,
            eq_join_conjuncts = list<struct>[1] {
                [0] = TEqJoinCondition {
                    01 left = TExpr {
                        01: nodes = list<struct>[1] {
                            [0] == TExprNode {
                                01: node_type (i32) = SLOT_REF,
                                02: type (struct) = TTypeDesc {
                                    01: type (i32) = VARCHAR,
                                }
                            }
                        }
                        36: label (string) = "KPI_ID",
                    },
                    02: right = TExpr {
                        01: nodes (list) = list<struct>[1] {
                            [0] = TExprNode {
                                01: node_type (i32) = SLOT_REF,
                                02: type (struct) = TTypeDesc {
                                    01: type (i32) = VARCHAR,
                                }
                            }
                        }
                        36: label (string) = "KPI_ID",
                    }
                },
            }
        }   
    }
    [2] TPlanNode {
        node_id = 3,
        node_type = EXCHANGE_NODE
    },
    [2] TPlanNode {
        node_id = 1,
        node_type = EXCHANGE_NODE
    }
    05: output_sink (struct) = TDataSink {
      01: type (i32) = 0,
      02: stream_sink (struct) = TDataStreamSink {
        01: dest_node_id (i32) = 6,
        02: output_partition (struct) = TDataPartition {
          01: type (i32) = 0,
          02: partition_exprs (list) = list<struct>[0] {
          },
        },
        11: tablet_sink_txn_id (i64) = -1,
      },
    },
}
```

```cpp
Status HashJoinBuildSinkOperatorX::init(const TPlanNode& tnode, RuntimeState* state) {
    const std::vector<TEqJoinCondition>& eq_join_conjuncts = tnode.hash_join_node.eq_join_conjuncts;
    for (const auto& eq_join_conjunct : eq_join_conjuncts) {
        vectorized::VExprContextSPtr build_ctx;
        RETURN_IF_ERROR(vectorized::VExpr::create_expr_tree(eq_join_conjunct.right, build_ctx));
        {
            // for type check
            vectorized::VExprContextSPtr probe_ctx;
            RETURN_IF_ERROR(vectorized::VExpr::create_expr_tree(eq_join_conjunct.left, probe_ctx));
            auto build_side_expr_type = build_ctx->root()->data_type();
            auto probe_side_expr_type = probe_ctx->root()->data_type();
        }
        _build_expr_ctxs.push_back(build_ctx);

        const auto vexpr = _build_expr_ctxs.back()->root();
    }
}
```
每个 `TEqJoinCondition.left` 表示 `probe` 侧需要执行的表达式，`TEqJoinCondition.left` 表示 `build` 侧需要执行的表达式。`ON A.KPI_ID = B.KPI_ID;` 这里的两个表达式都是 `SlotReference`。
```cpp
Status HashJoinBuildSinkOperatorX::sink(RuntimeState* state, vectorized::Block* in_block, bool eos) {
    if (local_state._should_build_hash_table) {
        ...
        RETURN_IF_ERROR(local_state._do_evaluate(*in_block, local_state._build_expr_ctxs,
                                                     *local_state._build_expr_call_timer,
                                                     res_col_ids))
        ...
    }

    if (local_state._should_build_hash_table && eos) {
        ...
        RETURN_IF_ERROR(
                local_state.process_build_block(state, (*local_state._shared_state->build_block)));
        ...
    }
}
```
构建 hash 表之前，需要等齐所有的数据，然后才开始构建 hash 表
```cpp
Status HashJoinBuildSinkLocalState::process_build_block(RuntimeState* state,
                                                        vectorized::Block& block)
{
    ...
    // 根据 hash 表的类型，决定调用什么 Hash 构造方法
}   
```
## Hash Table 操作

```plantuml

struct JoinSharedState {
    + join_op_variants : JoinOpVariants
}

struct HashJoinSharedState {
    - is_null_safe_eq_join : std::vector<bool>
    - store_null_in_hash_table : std::vector<bool>
    - arena : AreanPtr
    - hash_table_variants : HashTableVariants
    - build_block : std::shared_ptr<vectorized::Block>
}

struct MethodBaseInner {
    + hash_table : std::shared_ptr<HashMap>
    + arena : Arena
    + hash_values : std::vector<size_t>
    + bucket_nums : std::vector<UInt32>
    + [abstract] reset() : void
    + [abstract] init_serialized_keys(...) : void
    + [abstract] serialized_keys_size(bool) : void
    + [abstract] insert_keys_into_columns(std::vector<Key>& keys, MutableColumns& key_columns, size_t num_rows) : void
    ...
}

struct MethodBase {
    + init_iterator() : void
}



HashJoinSharedState -up-> JoinSharedState

HashJoinSharedState *-- MethodBaseInner

MethodBase -up-> MethodBaseInner
MethodSerialized  -up-> MethodBase
MethodStringNoCache -up-> MethodBase
MethodOneNumber -up-> MethodBase
```
```cpp
using JoinOpVariants =
        std::variant<std::integral_constant<TJoinOp::type, TJoinOp::INNER_JOIN>,
        std::integral_constant<TJoinOp::type, TJoinOp::LEFT_SEMI_JOIN>
        ...>;
using HashTableVariants = 
        std::variant<std::monostate, I8HashTableContext, ...>;
```

以 Int32 为例，其 HashTableContext 中保存的 HashTableVairants 类型为 I32HashTableContext
```cpp
template <class I32HashTableContext>
struct ProcessHashTableBuild {
    ProcessHashTableBuild(int rows, vectorized::ColumnRawPtrs& build_raw_ptrs,
                          HashJoinBuildSinkLocalState* parent, int batch_size, RuntimeState* state)
            : _rows(rows),
              _build_raw_ptrs(build_raw_ptrs),
              _parent(parent),
              _batch_size(batch_size),
              _state(state) {}

    template <int JoinOpType, bool ignore_null, bool short_circuit_for_null,
              bool with_other_conjuncts>
    Status run(I32HashTableContext& hash_table_ctx, vectorized::ConstNullMapPtr null_map,
               bool* has_null_key) {
        // 跳过对 null 的处理
        hash_table_ctx.hash_table->template prepare_build<JoinOpType>(_rows, _batch_size,
                                                                      *has_null_key);
        ...
        hash_table_ctx.init_serialized_keys(_build_raw_ptrs, _rows,
                                            null_map ? null_map->data() : nullptr, true, true,
                                            hash_table_ctx.hash_table->get_bucket_size());


    }
}
```
`be/src/vec/common/hash_table/hash_map_context.h`
```cpp
// be/src/vec/common/hash_table/hash_map_context.h

using I32HashTableContext = vectorized::PrimaryTypeHashTableContext<vectorized::UInt32>;

template <class T>
using PrimaryTypeHashTableContext = MethodOneNumber<T, JoinHashMap<T, HashCRC32<T>>>;

/// For the case where there is one numeric key.
/// FieldType is UInt8/16/32/64 for any type with corresponding bit width.
template <typename FieldType, typename TData>
struct MethodOneNumber : public MethodBase<TData> {
    using Base = MethodBase<TData>;
    using Base::init_iterator;
    using Base::hash_table;
    using State = ColumnsHashing::HashMethodOneNumber<typename Base::Value, typename Base::Mapped,
                                                      FieldType>;

    void init_serialized_keys(const ColumnRawPtrs& key_columns, size_t num_rows,
                              const uint8_t* null_map = nullptr, bool is_join = false,
                              bool is_build = false, uint32_t bucket_size = 0) override {
        Base::keys = (FieldType*)(key_columns[0]->is_nullable()
                                          ? assert_cast<const ColumnNullable*>(key_columns[0])
                                                    ->get_nested_column_ptr()
                                                    ->get_raw_data()
                                                    .data
                                          : key_columns[0]->get_raw_data().data);
        if (is_join) {
            Base::init_join_bucket_num(num_rows, bucket_size, null_map);
        } else {
            Base::init_hash_values(num_rows, null_map);
        }
    }

    void insert_keys_into_columns(std::vector<typename Base::Key>& input_keys,
                                  MutableColumns& key_columns, const size_t num_rows) override {
        if (!input_keys.empty()) {
            // If size() is ​0​, data() may or may not return a null pointer.
            key_columns[0]->insert_many_raw_data((char*)input_keys.data(), num_rows);
        }
    }
};
```

```cpp
template <typename Key, typename Hash = DefaultHash<Key>>
class JoinHashTable {
public:
    size_t hash(const Key& x) const { return Hash()(x); }

    static uint32_t calc_bucket_size(size_t num_elem) {
        size_t expect_bucket_size = num_elem + (num_elem - 1) / 7;
        return phmap::priv::NormalizeCapacity(expect_bucket_size) + 1;
    }

    template <int JoinOpType>
    void prepare_build(size_t num_elem, int batch_size, bool has_null_key) {
        _has_null_key = has_null_key;

        // the first row in build side is not really from build side table
        _empty_build_side = num_elem <= 1;
        max_batch_size = batch_size;
        bucket_size = calc_bucket_size(num_elem + 1);
        first.resize(bucket_size + 1);
        next.resize(num_elem);

        if constexpr (JoinOpType == TJoinOp::FULL_OUTER_JOIN ||
                      JoinOpType == TJoinOp::RIGHT_OUTER_JOIN ||
                      JoinOpType == TJoinOp::RIGHT_ANTI_JOIN ||
                      JoinOpType == TJoinOp::RIGHT_SEMI_JOIN) {
            visited.resize(num_elem);
        }
    }

    template <int JoinOpType, bool with_other_conjuncts>
    void build(const Key* __restrict keys, const uint32_t* __restrict bucket_nums,
               size_t num_elem) {
        build_keys = keys;
        for (size_t i = 1; i < num_elem; i++) {
            uint32_t bucket_num = bucket_nums[i];
            next[i] = first[bucket_num];
            first[bucket_num] = i;
        }
        if constexpr ((JoinOpType != TJoinOp::NULL_AWARE_LEFT_ANTI_JOIN &&
                       JoinOpType != TJoinOp::NULL_AWARE_LEFT_SEMI_JOIN) ||
                      !with_other_conjuncts) {
            /// Only null aware join with other conjuncts need to access the null value in hash table
            first[bucket_size] = 0; // index = bucket_num means null
        }
    }

private:
    const Key* build_keys;
    std::vector<uint8_t> visited;
    uint32_t bucket_size = 1;
    int max_batch_size = 4064;

    std::vector<uint32_t> first = {0};
    std::vector<uint32_t> next = {0};
    // use in iter hash map
    mutable uint32_t iter_idx = 1;
    vectorized::Arena* pool;
    bool _has_null_key = false;
    bool _empty_build_side = true;
}


```