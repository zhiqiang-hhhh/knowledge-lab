## OR 表达式作为谓词时是怎么执行的

```sql
SELECT * FROM tbl WHERE A OR B
```
* A 和 B 都可以通过索引分析得到结果
    
把两个结果做 UNION。
* A 可以走索引，B 对应的列上没有索引

需要想明白一个基本认知：由于这里是 `OR` 关系，那么不论是合取范式还是析取范式，为了计算表达式 B，B 涉及到的列一定是需要执行全表扫描的。剩下的问题就是 A 怎么处理。

### Apache Doris
1. A 表达式在索引分析阶段正常执行，可以得到一个 segment 级别的 row-bitmap（索引是 segment 粒度的）
2. 在每个 batch 的 read 之前，把 row-bitmap 转成一个 `ColumnBoolean`，表示当前 block 中的哪些行是满足要求的。
2. B 表达式需要按 batch 做计算，等于执行全表扫描
3. 在 batch 读阶段，A 表达式做的是短路计算，根据之前得到的 ColumnBoolean 判断当前 batch 中的 i 行是否符合要求（fast execute）

#### 相关代码
```cpp
class IndexExecContext {
    // A map of expressions to their corresponding inverted index result bitmaps.
    std::unordered_map<const vectorized::VExpr*, segment_v2::InvertedIndexResultBitmap>
            _index_result_bitmap;
}
```
`_index_result_bitmap` 保存 Expr* 到 segment 级别的 row-bitmap。

* batch read

```cpp
Status SegmentIterator::_next_batch_internal(vectorized::Block* block) {
    ...
    RETURN_IF_ERROR(_process_common_expr(_sel_rowid_idx.data(), _selected_size, block));
    ...
}

Status SegmentIterator::_process_common_expr(uint16_t* sel_rowid_idx, uint16_t& selected_size, vectorized::Block* block) {
    ...
    _output_index_result_column_for_expr(_sel_rowid_idx.data(), _selected_size, block);
    RETURN_IF_ERROR(_execute_common_expr(_sel_rowid_idx.data(), _selected_size, block));
}

Status SegmentIterator::_output_index_result_column_for_expr(_sel_rowid_idx.data(), 
_selected_size, block) {
    for (auto& expr_ctx : _common_expr_ctxs_push_down) {
        ...
        for (uint32_t i = 0; i < select_size; i++) {
            auto rowid = sel_rowid_idx ? _block_rowids[sel_rowid_idx[i]] : _block_rowids[i];
            if (index_result_bitmap) {
                vec_match_pred[i] = index_result_bitmap->containsBulk(bulk_context, rowid);
            }
            if (null_map_data != nullptr && null_bitmap->contains(rowid)) {
                (*null_map_data)[i] = 1;
                vec_match_pred[i] = 0;
            }
        }
        ...
        expr_ctx->get_index_context()->set_index_result_column_for_expr(
                        expr, std::move(index_result_column));
    }
}
```
在每个 batch 上计算谓词之前，在 `_output_index_result_column_for_expr` 函数里面计算当前 batch 里，哪些行是应该被谓词 A 保留的，结果保存到 `_index_result_column` 里面。

* fast_execute
```cpp
bool VExpr::fast_execute(VExprContext* context, ColumnPtr& result_column) const {
    if (context->get_index_context() &&
        context->get_index_context()->get_index_result_column().contains(this)) {
        // prepare a column to save result
        result_column = context->get_index_context()->get_index_result_column()[this];
        if (_data_type->is_nullable()) {
            result_column = make_nullable(result_column);
        }
        return true;
    }
    return false;
}
```