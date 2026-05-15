```plantuml
class VExprContext {
  + Status prepare(RuntimeState* state, const RowDescriptor& row_desc);
  + Status open(RuntimeState* state);
  + Status clone(RuntimeState* state, VExprContextSPtr& new_ctx);
  + Status execute(Block* block, int* result_column_id);
  + VExprSPtr _root;
}

class VExpr {
  + Status prepare(RuntimeState* state, const RowDescriptor& row_desc, VExprContext* context)
  + Status open(RuntimeState* state, VExprContext* context,
                        FunctionContext::FunctionStateScope scope);
  + Status execute(VExprContext* context, Block* block, int* result_column_id)
  + Status evaluate_inverted_index(VExprContext* context, uint32_t segment_num_rows)
  + Status execute_runtime_fitler(VExprContext* context, Block* block,
                                          int* result_column_id, ColumnNumbers& args)
  TExprNodeType::type _node_type;
  TExprOpcode::type _opcode;
  TFunction _fn;
  VExprSPtrs _children; // in few hundreds
}

struct TExprNodeType {
  XXX_LITERAL
  SLOT_REF
  MATCH_PRED
  ...
}

struct TExprOpcode {
  COMPOUND_NOT = 1,
  COMPOUND_AND = 2,
  COMPOUND_OR = 3,
  ...
}

VExprContext *-- VExpr
VExpr *-right- TExprNodeType
VExpr *-right- TExprOpcode
VExpr *-right- TFunction
```

`select count(CounterID) from hits_10m where CounterID in (4679,75171)`

上述 sql 中 `OLAP_SCAN_NODE` 对应在 BE 上看到的 Plan 精简后如下所示：

```text
[1] = TPlanNode {
          01: node_id = 0,
          02: node_type = OLAP_SCAN_NODE,
          07: conjuncts = {
            [0] = TExpr {
              01: nodes = {
                [0] = TExprNode {
                  01: node_type = IN_PRED,
                  02: TTypeDesc {
                    01: types = {
                      [0] = TTypeNode {
                        02: scalar_type = TScalarType {
                          01: type = BOOLEAN,
                        },
                      },
                    },
                  },
                  03: opcode = FILTER_IN,
                  04: num_children = 3,
                  11: in_predicate (struct) = TInPredicate {
                    01: is_not_in (bool) = false,
                  },
                },
                [1] = TExprNode {
                  01: node_type = SLOT_REF,
                  02: TTypeDesc {
                    01: types {
                      [0] = TTypeNode {
                        02: scalar_type (struct) = TScalarType {
                          01: type = INT,
                        },
                      },
                    },
                  },
                  04: num_children (i32) = 0,
                  15: slot_ref (struct) = TSlotRef {
                    01: slot_id (i32) = 0,
                    02: tuple_id (i32) = 0,
                    03: col_unique_id (i32) = 0,
                  },
                  36: label (string) = "CounterID",
                },
                [2] = TExprNode {
                  01: node_type = INT_LITERAL,
                  02: type (struct) = TTypeDesc {
                    01: types = TScalarType {
                      [0] = TTypeNode {
                        02: scalar_type (struct) = TScalarType {
                          01: type = INT,
                        },
                      },
                    },
                  },
                  04: num_children (i32) = 0,
                  10: int_literal = TIntLiteral {
                    01: value (i64) = 4679,
                  },
                },
                [3] = TExprNode {
                  01: node_type (i32) = INT_LITERAL,
                  02: type (struct) = TTypeDesc {
                    01: types (list) = list<struct>[1] {
                      [0] = TTypeNode {
                        02: scalar_type (struct) = TScalarType {
                          01: type = INT,
                        },
                      },
                    },
                  },
                  04: num_children (i32) = 0,
                  10: int_literal (struct) = TIntLiteral {
                    01: value (i64) = 75171,
                  },
                },
              },
            },
          },
}
```
`Operator` 对 `conjunct` 的处理是公用的代码如下：
```cpp
Status OperatorXBase::init(const TPlanNode& tnode, RuntimeState* /*state*/) {
    ...
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
    ...
}
```
任何布尔表达式都可以转换成：

* CNF（Conjunctive Normal Form，合取范式）

最终是 AND，里面的每一项是 OR 子句： `(a ∨ b ∨ c) ∧ (d ∨ e)`

* DNF（Disjunctive Normal Form，析取范式）

最终是 OR，里面是 AND 子句：`(a ∧ b) ∨ (c ∧ d)`

Doris 在处理谓词的时候采用的是合取范式，即优化器会把一组谓词拆成一个或者多个子表达式，最终的结果要求执行层对每个子表达式求AND。

比如对于 `WHERE a > 10 AND b = 3 AND (c = 1 OR c = 2)` Doris 优化器会把它的结构改成
```
conjuncts = [
    a > 10,
    b = 3,
    (c = 1 OR c = 2)
]
```


代码中的 conjuncts 就是组成合取范式的基本表达式。

```cpp
template <typename Derived>
Status ScanLocalState<Derived>::_normalize_conjuncts(RuntimeState* state) {
    ...
    for (auto it = _conjuncts.begin(); it != _conjuncts.end();) {
        auto& conjunct = *it;
        // A. If this conjunct has an expression, normally true
        if (conjunct->root()) {
            vectorized::VExprSPtr new_root;
            RETURN_IF_ERROR(_normalize_predicate(conjunct->root(), conjunct.get(), new_root));
            if (new_root) {
                conjunct->set_root(new_root);
                if (_should_push_down_common_expr() &&
                    vectorized::VExpr::is_acting_on_a_slot(*(conjunct->root()))) {
                    _common_expr_ctxs_push_down.emplace_back(conjunct);
                    it = _conjuncts.erase(it);
                    continue;
                }
            } else { // All conjuncts are pushed down as predicate column
                _stale_expr_ctxs.emplace_back(conjunct);
                it = _conjuncts.erase(it);
                continue;
            }
        }
        ++it;
    }
    ...
}

template <typename Derived>
Status ScanLocalState<Derived>::_normalize_predicate(
    const vectorized::VExprSPtr& conjunct_expr_root, vectorized::VExprContext* context,
        vectorized::VExprSPtr& output_expr) {
    ...
}
```
`_normalize_conjuncts`的作用是把谓词转成归一化的 ColumnValueRange。

在 `OlapScanLocalState::_build_key_ranges_and_filters` 里面，如果某个 key 列上有谓词，会尝试从 ColumnValueRange 里面提取出一个 ScanKey
·_build_key_ranges_and_filters 里面转成 key range 或者 filter

```cpp
OlapScanLocalState::_build_key_ranges_and_filters() {
  ...
  for (int idx = 0; idx < key_column_names.size(); ++idx) {
    auto iter = _colname_to_value_range.find(column_names[idx]);

  }
  const auto& column_value_range = iter->second;

  RETURN_IF_ERROR(std::visit(
      [&](auto&& range) {
          // make a copy or range and pass to extend_scan_key, keep the range unchanged
          // because extend_scan_key method may change the first parameter.
          // but the original range may be converted to olap filters, if it's not a exact_range.
          auto temp_range = range;
          if (range.get_fixed_value_size() <= p._max_pushdown_conditions_per_column) {
              RETURN_IF_ERROR(
                      _scan_keys.extend_scan_key(temp_range, p._max_scan_key_num,
                                                  &exact_range, &eos, &should_break));
              if (exact_range) {
                  _colname_to_value_range.erase(iter->first);
              }
          } else {
              // if exceed max_pushdown_conditions_per_column, use whole_value_rang instead
              // and will not erase from _colname_to_value_range, it must be not exact_range
              temp_range.set_whole_value_range();
              RETURN_IF_ERROR(
                      _scan_keys.extend_scan_key(temp_range, p._max_scan_key_num,
                                                  &exact_range, &eos, &should_break));
          }
          return Status::OK();
      },
      column_value_range));
  ...
  for (auto& iter : _colname_to_value_range) {
    std::vector<FilterOlapParam<TCondition>> filters;
    std::visit([&](auto&& range) { range.to_olap_filter(filters); }, iter.second);

    for (const auto& filter : filters) {
        _olap_filters.emplace_back(filter);
    }
  }
}
```
```cpp
class OlapScanKeys {
  ...
  std::vector<OlapTuple> _begin_scan_keys;
  std::vector<OlapTuple> _end_scan_keys;
  bool _has_range_value;
  bool _begin_include;
  bool _end_include;
  bool _is_convertible;
};

class OlapTuple {
  ...
  std::vector<std::string> _values;
  std::vector<bool> _nulls;
}

Status OlapScanKeys::extend_scan_key(ColumnValueRange<primitive_type>& range,
                                     int32_t max_scan_key_num, bool* exact_value, bool* eos,
                                     bool* should_break) {
    
}
```
OlapScanKeys 的核心数据成员是一个二维数组。其中，_begin_scan_keys 的 size 等于 谓词中涉及到的key列的数量，每一个 key 列对应一个 OlapTuple。
一个 key 列可能被多个谓词同时读，所以每一个 OlapTuple 都是一个数组。

```cpp
Status OlapScanKeys::get_key_range(std::vector<std::unique_ptr<OlapScanRange>>* key_range) {}
```





```plantuml
class ColumnValueRange {
  - _column_name : string
  - _column_type : PrimitiveType    // Column type eg: TINYINT,SMALLINT,INT,BIGINT
  - _low_value : CppType ;         // Column's low value, closed interval at left
  - _high_value : CppType ;        // Column's high value, open interval at right
  - _low_op : SQLFilterOp ;
  - _high_op : SQLFilterOp ;
  - _fixed_values : set<CppType> ; // Column's fixed int value
  - _is_nullable_col : bool
  - _contain_null : bool  
  - _precision : int
  - _scale : int
  - _marked_runtime_filter_predicate : bool
  + to_olap_filter(vector<TCondition>& filters) : void
}

class TCondition {
  - column_name : string
  - condition_op : string
  - condition_values : vector<string>
  - column_unique_id : int
  - marked_by_runtime_filter : bool
  - compound_type : TCompoundType
}

class OlapScanKeys {
  - vector<OlapTuple> _begin_scan_keys;
  - vector<OlapTuple> _end_scan_keys;
  - bool _has_range_value;
  - bool _begin_include;
  - bool _end_include;
  - bool _is_convertible;
}

OlapScanKeys *-- OlapTuple

class OlapTuple {
  std::vector<std::string> _values;
  std::vector<bool> _nulls;
}

struct KeyRange {
  - const RowCursor* lower_key = nullptr;
  - bool include_lower;
  - const RowCursor* upper_key = nullptr;
  - bool include_upper;
}

class StorageReadOptions {
  - std::vector<KeyRange> key_ranges;
}

StorageReadOptions *-right- KeyRange

class SegmentIterator {
  StorageReadOptions _opts;
  std::vector<ColumnPredicate*> _col_predicates;
  Status SegmentIterator::init(const StorageReadOptions& opts);
}

class BetaRowsetReader {
  - RowsetReaderContext* _read_context
  - std::unique_ptr<RowwiseIterator> _iterator;
  - StorageReadOptions _read_options;
}

BetaRowsetReader *-down- StorageReadOptions
BetaRowsetReader *-down- RowwiseIterator
SegmentIterator -up-> RowwiseIterator
SegmentIterator *-right- StorageReadOptions
```

```cpp
BetaRowsetReader::_init_iterator()


/// Here do not use the argument of `opts`,
/// see where the iterator is created in `BetaRowsetReader::get_segment_iterators`
Status LazyInitSegmentIterator::init(const StorageReadOptions& /*opts*/) {
    _need_lazy_init = false;
    if (_inner_iterator) {
        return Status::OK();
    }

    RETURN_IF_ERROR(_segment->new_iterator(_schema, _read_options, &_inner_iterator));
    return _inner_iterator->init(_read_options);
}
```


```plantuml
interface ColumnPredicate {
#  Status evaluate(
    const vectorized::IndexFieldNameAndTypePair& name_with_type,InvertedIndexIterator* iterator, uint32_t num_rows, roaring::Roaring* bitmap)
}
class MatchPredicate {

}

MatchPredicate -up-> ColumnPredicate
```

```text

BetaRowsetReader::next_block
|
|-BetaRowsetReader::_init_iterator_once()
  |
  |-BetaRowsetReader::_init_iterator()
  |
  |-LazyInitSegmentIterator::init
    |-Segment::new_iterator
      |-SegmentIterator::init
      |
      |-SegmentIterator::init_iterators()
        |
        |-SegmentIterator::_init_index_iterators()
        |
        |-Segment::new_index_iterator
          |
          |-_inverted_index_file_reader = std::make_shared<InvertedIndexFileReader>
          |
          |-ColumnReader::_ensure_inverted_index_loaded(_inverted_index_file_reader)
          | |
          | |-ColumnReader::_load_inverted_index
          |   |
          |   |-_inverted_index_reader = InvertedIndexReader::create_shared（倒排索引这里的实现很奇怪，只是创建了 reader 没有真正读盘构建内存索引）
          |
          |-_inverted_index_iterator = ColumnReader::new_inverted_index_iterator




SegmentIterator::_next_batch_internal(vectorized::Block* block)
|
|-SegmentIterator::_lazy_init()
| |
| |-SegmentIterator::_get_row_ranges_by_column_conditions()
|   |
|   |-SegmentIterator::_apply_index_expr()
|   |
|   |-SegmentIterator::_get_row_ranges_from_conditions()
|
|    
|
|-SegmentIterator::_read_columns_by_index

```


```TExprNodeType
ScanLocalState::open
|
|-RuntimeFilterConsumerHelper::acquire_runtime_filter
  |
  |-RuntimeFilterConsumer::acquire_expr
    |
    |-RuntimeFilterConsumer::_apply_ready_expr
      |
      |-VRuntimeFilterWrapper::attach_profile_counter
|
|-process_conjuncts()
```


---------

1. 根据扫描目标列的类型初始化每个列需要扫描的值的范围
2. 根据谓词去更新每个列的值的范围






