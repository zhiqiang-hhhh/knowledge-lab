## Doris 排序键查询优化的代码实现

Doris 通过排序键优化查询性能主要包括以下几个核心机制：

### 1. Short Key Index（前缀索引）

**代码位置**: short_key_index.h

```cpp
// ShortKeyIndexDecoder 负责解码 Short Key 索引
// 支持 lower_bound 和 upper_bound 操作，快速定位数据块
ShortKeyIndexIterator lower_bound(const Slice& key) const;
ShortKeyIndexIterator upper_bound(const Slice& key) const;
```

**使用逻辑**: segment_iterator.cpp

```cpp
// 通过 Short Key Index 查找数据的 ordinal 位置
// 1. 先用 lower_bound/upper_bound 定位到索引块
// 2. 再用二分查找找到精确位置
Status SegmentIterator::_lookup_ordinal_from_sk_index(const RowCursor& key, bool is_include,
                                                      rowid_t upper_bound, rowid_t* rowid) {
    const ShortKeyIndexDecoder* sk_index_decoder = _segment->get_short_key_index();
    // ...
    auto start_iter = sk_index_decoder->lower_bound(index_key);
    // 二分查找精确定位
    while (start < end) {
        rowid_t mid = (start + end) / 2;
        RETURN_IF_ERROR(_seek_and_peek(mid));
        int cmp = _compare_short_key_with_seek_block(key_col_ids);
        // ...
    }
}
```

### 2. Zone Map 索引剪枝

**代码位置**: column_reader.cpp

Zone Map 存储每个数据页的 min/max 值，用于快速跳过不满足条件的数据页：

```cpp
Status ColumnReader::_get_filtered_pages(
        const AndBlockColumnPredicate* col_predicates,
        const std::vector<std::shared_ptr<const ColumnPredicate>>* delete_predicates,
        std::vector<uint32_t>* page_indexes, const ColumnIteratorOptions& iter_opts) {
    const std::vector<ZoneMapPB>& zone_maps = _zone_map_index->page_zone_maps();
    for (size_t i = 0; i < page_size; ++i) {
        RETURN_IF_ERROR(_parse_zone_map(zone_maps[i], min_value.get(), max_value.get()));
        // 判断谓词是否可能匹配该页的 [min, max] 区间
        if (_zone_map_match_condition(zone_maps[i], min_value.get(), max_value.get(), col_predicates)) {
            page_indexes->push_back(i);  // 只读取可能匹配的页
        }
    }
}
```

**调用链**: segment_iterator.cpp

```cpp
// 在 _get_row_ranges_from_conditions 中使用 Zone Map 过滤
// second filter data by zone map
for (const auto& cid : cids) {
    RETURN_IF_ERROR(_column_iterators[cid]->get_row_ranges_by_zone_map(
            _opts.col_id_to_predicates.at(cid).get(), ...));
    // intersect different columns's row ranges to get final row ranges by zone map
    RowRanges::ranges_intersection(zone_map_row_ranges, column_row_ranges, &zone_map_row_ranges);
}
```

### 3. TopN 查询优化 (利用存储层排序)

**FE 端判断逻辑**: PhysicalPlanTranslator.java

当 ORDER BY 列是排序键的前缀时，可以利用存储层已排序的特性：

```java
/**
 * topN opt: using storage data ordering to accelerate topn operation.
 * refer pr: optimize topn query if order by columns is prefix of sort keys of table (#10694)
 */
private boolean checkPushSort(SortNode sortNode, OlapTable olapTable) {
    // Ensure limit is less than threshold
    if (sortNode.getLimit() <= 0
            || sortNode.getLimit() > context.getSessionVariable().topnOptLimitThreshold) {
        return false;
    }
    // Tablet's order by key only can be the front part of schema.
    // Do **prefix match** to check if order by key can be pushed down.
    // olap order by key: a.b.c.d
    // sort key: (a) (a,b) (a,b,c) (a,b,c,d) is ok
    //           (a,c) (a,c,d), (a,c,b) is NOT ok
    for (int i = 0; i < sortExprs.size(); i++) {
        Column sortColumn = sortKeyColumns.get(i);
        // 检查 ORDER BY 列是否与表的排序键前缀匹配
        if (sortExpr instanceof SlotRef) {
            if (!sortColumn.equals(slotRef.getColumn())) {
                return false;
            }
        }
    }
    return true;
}
```

**BE 端 TopN 优化**: segment_iterator.cpp

```cpp
bool SegmentIterator::_can_opt_topn_reads() {
    if (_opts.topn_limit <= 0) {
        return false;
    }
    // 检查所有列是否都通过了倒排索引的条件
    bool all_true = std::ranges::all_of(_schema->column_ids(), [this](auto cid) {
        if (_check_all_conditions_passed_inverted_index_for_column(cid, true)) {
            return true;
        }
        return false;
    });
    return all_true;
}
```

使用时限制读取行数：
```cpp
if (_can_opt_topn_reads()) {
    nrows_read_limit = std::min(static_cast<uint32_t>(_opts.topn_limit), nrows_read_limit);
}
```

### 4. Defer Materialize (延迟物化)

**代码位置**: DeferMaterializeTopNResult.java

对于 TopN 查询，只需要先读取排序列和 rowid，排序后再根据 rowid 物化其他列：

```java
// 延迟物化只读取排序相关的列，过滤后再读取其他列
LogicalDeferMaterializeOlapScan deferOlapScan = new LogicalDeferMaterializeOlapScan(
        logicalOlapScan, deferredMaterializedExprIds, columnId);
```

### 5. Bloom Filter 索引

**代码位置**: column_reader.cpp

```cpp
Status ColumnReader::get_row_ranges_by_bloom_filter(const AndBlockColumnPredicate* col_predicates,
                                                    RowRanges* row_ranges, ...) {
    for (auto& pid : page_ids) {
        std::unique_ptr<BloomFilter> bf;
        RETURN_IF_ERROR(bf_iter->read_bloom_filter(pid, &bf));
        // 用 Bloom Filter 过滤不可能包含目标值的数据页
        if (col_predicates->evaluate_and(bf.get())) {
            bf_row_ranges.add(RowRange(...));
        }
    }
    RowRanges::ranges_intersection(*row_ranges, bf_row_ranges, row_ranges);
}
```

---

### 总结

| 优化机制 | 作用 | 关键代码 |
|---------|-----|---------|
| **Short Key Index** | 快速定位满足排序键条件的数据行范围 | `_lookup_ordinal_from_sk_index` |
| **Zone Map** | 跳过不满足条件的数据页 | `get_row_ranges_by_zone_map` |
| **TopN Push Down** | ORDER BY 是排序键前缀时直接读取已排序数据 | `checkPushSort` |
| **Defer Materialize** | 延迟物化非排序列，减少 I/O | `DeferMaterializeTopNResult` |
| **Bloom Filter** | 过滤不包含目标值的数据页 | `get_row_ranges_by_bloom_filter` |


### IndexPage

```plantuml
PagePointer
```

### KeyRange
KeyRange 是 doris 在 segment iterator 中用来描述可以被 short key index 加速的谓词的数据结构。
```cpp
struct KeyRange {
    // the lower bound of the range, nullptr if not existed
    const RowCursor* lower_key = nullptr;
    // whether `lower_key` is included in the range
    bool include_lower;
    // the upper bound of the range, nullptr if not existed
    const RowCursor* upper_key = nullptr;
    // whether `upper_key` is included in the range
    bool include_upper;
}

struct RowCursor {
    std::unique_ptr<Schema> _schema;

    char* _fixed_buf = nullptr; // point to fixed buf
    size_t _fixed_len;
    char* _owned_fixed_buf = nullptr; // point to buf allocated in init function

    char* _variable_buf = nullptr;
    size_t _variable_len;
    size_t _string_field_count;
    char** _long_text_buf = nullptr;
}
```

不论有多少个谓词，KeyRange 只有一个，KeyRang 的 lower_key 保存所有可以被 short key index 加速的谓词的上下界。比如：

```sql
CREATE TABLE `debug_pk_comp` (
  `a` int NULL,
  `b` int NULL,
  `val` int NULL
) ENGINE=OLAP
DUPLICATE KEY(`a`, `b`)
DISTRIBUTED BY HASH(`a`) BUCKETS 1
PROPERTIES (
"replication_allocation" = "tag.location.default: 1");

SELECT * FROM debug_pk_comp WHERE a = 2 AND b > 1 ORDER BY a,b;
```
谓词对应的 key range 表示为
```text
lower_key: 0&2|0&1, include_lower=0
upper_key: 0&2|0&2147483647, include_upper=1
```
RowCursor 的 debugString 的格式为
```text
is_null&value|is_numm&value...
```
因此 lower_key 和 upper_key 的第一组值组成了 `a = 2` 这个谓词，第二组值构成了 `1 < b < 2147483647` 这个谓词。
#### RowCursor
注意 RowCursor 这个类的实现里面用来描述key的数据结构是binary，这与short key index 的编码方式有关。
##### Short Key Index
假设某张表只有一个排序列，并且该排序列类行为 Int32，如果去实现设计实现一个 shory key index，那么最朴素的想法应该是使用 Int32 的内存格式作为 short key index 的存储格式。这样在读取 short key index 的 page 之后不需要解码，可以直接把这段 binary cast 成一个 cpp 的 Int32，然后去进行计算。
但是实际情况中，整型数字在内存中的编码有大端法和小端法的区别。
比如小端法机器上，整数的低字节在前，高字节在后，比如
```cpp
值 256 的小端存储：00 01 00 00
值 1   的小端存储：01 00 00 00
```
考虑这样一种情况：在小端法机器上完成写入，在大端法机器上进行计算。那么此时在大端法机器上 cast 得到的 cpp Int32 就不等于写入时候小端法机器的 Int32 了，此时在大端法机器上的 cast 结果为：


在大端法机器上直接 cast 这些字节：
```cpp
小端写入的 256：00 01 00 00  →  大端法 cast 结果：0x00010000 = 65536
小端写入的 1  ：01 00 00 00  →  大端法 cast 结果：0x01000000 = 16777216
```
此时解码得到的结果就错误了。
因此 short key index 不仅需要考虑查询时候的速度，还需要去解决跨平台编码解码的问题。
一种方式是，在 meta 里面记录写入机器的整数编码信息，对于大端法机器上写入的结果，如果查询也在大端机器，那么可以直接 cast binary to Int32，如果是在小端法机器上进行查询，那么就需要做一个转换，转换后再 cast。

还有一种方法是在写入的时候使用与平台无关的二进制编码方式，确保字节序的比较结果与数值比较一致，在查询期间直接基于 binary 进行比较（使用 memcmp），Doris 采用的是第二种方式。

当只有一个排序列的时候，方式一更好，因为首先导入阶段不需要编码没有额外的开销，其次虽然查询期间需要进行一次判断，但是这个开销很小，最差情况下查询与导入在不同平台发生的情况也很少。

但是当涉及到多个排序列的话，情况会发生变化。

**方案一（记录编码信息 + 按需转换）在多列场景下的问题：**

假设有两个排序列 `(a INT, b INT)`，需要比较两个复合键 `(1, 256)` 和 `(1, 1)`：
1. 首先需要对每个列单独解码（可能需要字节序转换）
2. 然后逐列比较：先比较 `a`，如果相等再比较 `b`
3. 比较逻辑变成：
```cpp
int compare(Key& k1, Key& k2) {
    int32_t a1 = decode_with_endian_check(k1.col_a);
    int32_t a2 = decode_with_endian_check(k2.col_a);
    if (a1 != a2) return a1 < a2 ? -1 : 1;
    
    int32_t b1 = decode_with_endian_check(k1.col_b);
    int32_t b2 = decode_with_endian_check(k2.col_b);
    return b1 < b2 ? -1 : (b1 > b2 ? 1 : 0);
}
```

随着列数增加，比较开销线性增长，且无法利用 memcmp 的 SIMD 优化。

**方案二（平台无关编码 + memcmp）在多列场景下的优势：**

如果在写入时对每个列都使用大端编码（Big-Endian），那么多列可以直接拼接成一个连续的 binary：
```cpp
// 复合键 (1, 256) 的编码：
// a=1:   00 00 00 01  (大端)
// b=256: 00 00 01 00  (大端)
// 拼接后：00 00 00 01 00 00 01 00

// 复合键 (1, 1) 的编码：
// a=1:   00 00 00 01  (大端)
// b=1:   00 00 00 01  (大端)
// 拼接后：00 00 00 01 00 00 00 01
```

比较时只需要一次 memcmp：
```cpp
int compare(Key& k1, Key& k2) {
    return memcmp(k1.data, k2.data, k1.length);
}
```

memcmp 结果：
```
00 00 00 01 00 00 01 00  vs  00 00 00 01 00 00 00 01
                  ↑                         ↑
                  01 > 00
→ memcmp 返回正数 → (1, 256) > (1, 1) ✓ 正确！
```

**多列场景下方案二的优势总结：**
| 特性 | 方案一 | 方案二 |
|-----|-------|-------|
| 比较次数 | O(n)，n为列数 | O(1)，一次 memcmp |
| SIMD 优化 | 无法利用 | memcmp 可利用 SIMD |
| 实现复杂度 | 需要知道列数、类型 | 只需知道总长度 |
| 二分查找 | 每次比较都需解码 | 直接在 binary 上二分 |

因此，Doris 选择方案二，在写入时将排序键编码为平台无关的 binary 格式，查询时直接使用 memcmp 进行比较。

##### Short Key Index 的前缀匹配限制

方案二（memcmp）虽然高效，但它要求 **谓词必须满足排序键的前缀匹配**，否则无法使用 Short Key Index。

假设表的排序键为 `(a, b)`，编码后的 Short Key 为：
```
row1: (a=1, b=1)   → 00 00 00 01 | 00 00 00 01
row2: (a=1, b=256) → 00 00 00 01 | 00 00 01 00
row3: (a=2, b=1)   → 00 00 00 02 | 00 00 00 01
row4: (a=2, b=256) → 00 00 00 02 | 00 00 01 00
```

**Case 1: `WHERE a = 1`（前缀匹配 ✓）**

可以构造 key range：
```
lower_key: 00 00 00 01 | 00 00 00 00  (a=1, b=MIN)
upper_key: 00 00 00 01 | FF FF FF FF  (a=1, b=MAX)
```
memcmp 可以快速定位到 row1、row2，Short Key Index 生效。

**Case 2: `WHERE a = 1 AND b > 100`（前缀匹配 ✓）**

可以构造 key range：
```
lower_key: 00 00 00 01 | 00 00 00 64  (a=1, b=100)
upper_key: 00 00 00 01 | FF FF FF FF  (a=1, b=MAX)
```
memcmp 可以快速定位到 row2，Short Key Index 生效。

**Case 3: `WHERE b = 256`（跳过第一列，前缀不匹配 ✗）**

问题：`b=256` 的编码 `00 00 01 00` 分散在不同的 `a` 值下：
```
row2: 00 00 00 01 | 00 00 01 00  (a=1)
row4: 00 00 00 02 | 00 00 01 00  (a=2)
```

如果强行构造 key range，memcmp 比较时会先比较 `a` 列的字节，导致无法精确过滤。

**结论：无法通过 memcmp 精确过滤出 `b=256` 的行，Short Key Index 失效。**

**Case 4: `WHERE b > 100`（跳过第一列，前缀不匹配 ✗）**

同样的问题，`b > 100` 的行分散在不同的 `a` 值下，memcmp 无法跳过不满足条件的行。

**为什么方案一也无法解决这个问题？**

即使使用方案一（逐列比较），也无法利用 Short Key Index，因为：
1. Short Key Index 是按 `(a, b)` 的**复合顺序**排列的
2. 当只有 `b` 的谓词时，满足条件的行在 index 中是**不连续**的
3. 无论用什么比较方式，都无法在 B-tree 类型的索引上做范围查找

**解决方案：**

对于非前缀匹配的谓词，需要其他索引机制：
1. **Zone Map**：检查每个 page 的 `b` 列 min/max，跳过不可能包含目标值的 page
2. **Bloom Filter**：快速判断某个 page 是否可能包含 `b=256`
3. **Inverted Index（倒排索引）**：直接建立 `b` 列的索引，精确定位 rowid

这也是为什么 Doris 除了 Short Key Index 之外，还提供了 Zone Map、Bloom Filter、Inverted Index 等多种索引机制。