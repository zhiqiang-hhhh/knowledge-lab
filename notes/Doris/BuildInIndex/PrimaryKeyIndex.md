# Doris Primary Key Index

Primary Key Index 是 Doris 在 **Unique Key Merge-on-Write (MOW)** 模式下用于支持高效点查和去重的核心索引结构。

## 1. 索引粒度

### 1.1 行级粒度 (Row-Level Granularity)

**Primary Key Index 的粒度是行级别的**，即为每一行数据都构建索引条目。

```cpp
// be/src/olap/primary_key_index.cpp
Status PrimaryKeyIndexBuilder::add_item(const Slice& key) {
    RETURN_IF_ERROR(_primary_key_index_builder->add(&key));
    Slice key_without_seq = Slice(key.get_data(), key.get_size() - _seq_col_length - _rowid_length);
    RETURN_IF_ERROR(_bloom_filter_index_builder->add_values(&key_without_seq, 1));
    // the key is already sorted, so the first key is min_key, and
    // the last key is max_key.
    if (UNLIKELY(_num_rows == 0)) {
        _min_key.append(key.get_data(), key.get_size());
    }
    _num_rows++;
    _size += key.get_size();
    return Status::OK();
}
```

每次调用 `add_item` 就是为一行数据添加一个索引条目。

### 1.2 索引条目内容

每个索引条目包含：
- **Primary Key 列的编码值**: 所有 unique key 列经过 `full_encode_keys` 编码后的 binary string
- **Sequence Column** (可选): 用于支持 sequence 列的 merge-on-write
- **Row ID** (MOW with cluster key): 行在 segment 内的位置

```cpp
// be/src/olap/rowset/segment_v2/segment_writer.cpp
std::string key = _full_encode_keys(primary_key_coders, primary_key_columns, pos);
_maybe_invalid_row_cache(key);
if (_tablet_schema->has_sequence_col()) {
    _encode_seq_column(seq_column, pos, &key);
}
RETURN_IF_ERROR(_primary_key_index_builder->add_item(key));
```

## 2. 索引条目的 Key 和 Value

Primary Key Index 包含两层结构，每层的 key/value 含义不同：

### 2.1 Data Page 层 (存储实际数据)

**Data Page 存储的是原始的 Primary Key 值本身**，不是 key-value 结构：

| 内容 | 说明 |
|------|------|
| **存储内容** | 有序排列的 Primary Key 编码值 |
| **每条记录** | `encoded_primary_key + [seq_col] + [rowid]` |

```cpp
// 每行数据的 key 编码内容
std::string key = _full_encode_keys(primary_key_columns, pos);  // Primary Key 各列编码
if (_tablet_schema->has_sequence_col()) {
    _encode_seq_column(seq_column, pos, &key);  // 追加 sequence column
}
// 对于 MOW with cluster key，还会追加 rowid
_encode_rowid(pos, &key);
```

**查询时**：通过二分查找在 Data Page 内定位 key，返回的是该 key 在 page 内的 **offset**，结合 `first_ordinal` 得到全局 **row_id (ordinal)**。

### 2.2 Index Page 层 (B-Tree 索引)

Index Page 是真正的 key-value 结构，用于快速定位 Data Page：

#### Value Index (按 Primary Key 查找)

| Key | Value |
|-----|-------|
| Data Page 的**第一个 Primary Key** (编码后) | **PagePointer** (页面在文件中的位置) |

```cpp
// be/src/olap/rowset/segment_v2/indexed_column_writer.cpp
if (_options.write_value_index) {
    std::string key;
    _value_key_coder->full_encode_ascending(_first_value.data(), &key);  // Page 的第一个 key
    _value_index_builder->add(key, _last_data_page);  // value 是 PagePointer
}
```

#### Ordinal Index (按 Row ID 查找)

| Key | Value |
|-----|-------|
| Data Page 的 **first_ordinal** (uint64编码) | **PagePointer** (页面在文件中的位置) |

```cpp
if (_options.write_ordinal_index) {
    std::string key;
    KeyCoderTraits<OLAP_FIELD_TYPE_UNSIGNED_BIGINT>::full_encode_ascending(&first_ordinal, &key);
    _ordinal_index_builder->add(key, _last_data_page);  // value 是 PagePointer
}
```

### 2.3 PagePointer 结构

```cpp
// Index 的 Value: 指向 Data Page 在文件中的位置
struct PagePointer {
    uint64_t offset;  // 文件内偏移
    uint32_t size;    // 页面大小
};
```

### 2.4 Index Page 的物理格式

```
IndexPageBody := IndexEntry^NumEntry
IndexEntry := KeyLength(vint) + Key(bytes) + PageOffset(vlong) + PageSize(vint)
```

### 2.5 完整示例

假设有 5 个 Primary Key: `["aaa", "bbb", "ccc", "ddd", "eee"]`，每 2 个 key 一个 Data Page：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Value Index (B-Tree)                           │
│  ┌─────────────────┬─────────────────┬─────────────────┐           │
│  │ Key="aaa"       │ Key="ccc"       │ Key="eee"       │           │
│  │ Val=PP(page0)   │ Val=PP(page1)   │ Val=PP(page2)   │           │
│  └────────┬────────┴────────┬────────┴────────┬────────┘           │
│           ↓                 ↓                 ↓                     │
├───────────┼─────────────────┼─────────────────┼─────────────────────┤
│  Data Page 0        Data Page 1        Data Page 2                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │ "aaa" (ord=0)│   │ "ccc" (ord=2)│   │ "eee" (ord=4)│               │
│  │ "bbb" (ord=1)│   │ "ddd" (ord=3)│   │             │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘

查询 "ccc" 的流程:
1. Value Index: seek_at_or_before("ccc") → 找到 Key="ccc", Val=PP(page1)
2. 读取 Data Page 1
3. 在 Page 1 内二分查找 "ccc" → offset=0
4. row_id = first_ordinal(2) + offset(0) = 2
```

## 3. 索引算法结构

### 3.1 整体架构

Primary Key Index 采用类似 **RocksDB Partitioned Index** 的设计，由以下部分组成：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Primary Key Index Structure                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    IndexedColumnWriter                        │   │
│  │  (核心写入组件 - 分层索引结构)                                   │   │
│  ├──────────────────────────────────────────────────────────────┤   │
│  │                                                               │   │
│  │   ┌─────────────────────────────────────────────────────┐    │   │
│  │   │              Value Index (B-Tree)                    │    │   │
│  │   │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │    │   │
│  │   │  │Key1→PP1│  │Key2→PP2│  │Key3→PP3│  │Key4→PP4│    │    │   │
│  │   │  └────────┘  └────────┘  └────────┘  └────────┘    │    │   │
│  │   └─────────────────────────────────────────────────────┘    │   │
│  │                          ↓                                    │   │
│  │   ┌─────────────────────────────────────────────────────┐    │   │
│  │   │              Data Pages (Sorted Keys)                │    │   │
│  │   │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │    │   │
│  │   │  │Page 0  │  │Page 1  │  │Page 2  │  │Page 3  │    │    │   │
│  │   │  │Keys... │  │Keys... │  │Keys... │  │Keys... │    │    │   │
│  │   │  └────────┘  └────────┘  └────────┘  └────────┘    │    │   │
│  │   └─────────────────────────────────────────────────────┘    │   │
│  │                                                               │   │
│  │   ┌─────────────────────────────────────────────────────┐    │   │
│  │   │              Ordinal Index (B-Tree)                  │    │   │
│  │   │  (Optional - 支持按 rowid 定位)                       │    │   │
│  │   └─────────────────────────────────────────────────────┘    │   │
│  │                                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Bloom Filter Index                         │   │
│  │  (快速判断 key 是否可能存在，FPP = 0.01)                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 IndexedColumnWriter - 核心写入组件

```cpp
// be/src/olap/rowset/segment_v2/indexed_column_writer.h
struct IndexedColumnWriterOptions {
    size_t index_page_size = 64 * 1024;     // Index Page 大小: 64KB
    size_t data_page_size = 1024 * 1024;    // Data Page 大小: 1MB (但 PK Index 用 32KB)
    bool write_ordinal_index = false;        // 是否写 ordinal index
    bool write_value_index = false;          // 是否写 value index
    EncodingTypePB encoding = DEFAULT_ENCODING;
    CompressionTypePB compression = NO_COMPRESSION;
};
```

Primary Key Index 的初始化配置：

```cpp
// be/src/olap/primary_key_index.cpp
Status PrimaryKeyIndexBuilder::init() {
    const auto* type_info = get_scalar_type_info<FieldType::OLAP_FIELD_TYPE_VARCHAR>();
    segment_v2::IndexedColumnWriterOptions options;
    options.write_ordinal_index = true;   // 支持按 ordinal (row id) 查找
    options.write_value_index = true;     // 支持按 value (primary key) 查找
    options.data_page_size = config::primary_key_data_page_size;  // 默认 32KB
    options.encoding = segment_v2::EncodingInfo::get_default_encoding(...);
    options.compression = segment_v2::ZSTD;  // 使用 ZSTD 压缩
    // ...
}
```

### 2.3 Data Page 结构

每个 Data Page 存储一批有序的 Primary Key：

```cpp
// be/src/olap/rowset/segment_v2/indexed_column_writer.cpp
Status IndexedColumnWriter::_finish_current_data_page(size_t& num_val) {
    auto num_values_in_page = _data_page_builder->count();
    ordinal_t first_ordinal = _num_values - num_values_in_page;

    // Page Body: 编码后的 key 数据
    OwnedSlice page_body;
    RETURN_IF_ERROR(_data_page_builder->finish(&page_body));

    // Page Footer: 元数据
    PageFooterPB footer;
    footer.set_type(DATA_PAGE);
    footer.mutable_data_page_footer()->set_first_ordinal(first_ordinal);
    footer.mutable_data_page_footer()->set_num_values(num_values_in_page);

    // 压缩并写入文件
    RETURN_IF_ERROR(PageIO::compress_and_write_page(...));
}
```

**Data Page 的配置参数**：
- 默认大小: `primary_key_data_page_size = 32768` (32KB)
- 可通过 BE 配置调整

### 2.4 Index Page 结构 (B-Tree)

Index Page 用于快速定位到目标 Data Page：

```cpp
// be/src/olap/rowset/segment_v2/index_page.h
// IndexPageBody := IndexEntry^NumEntry
// IndexEntry := KeyLength(vint), Byte^KeyLength, PageOffset(vlong), PageSize(vint)

class IndexPageBuilder {
    // 添加索引条目: key -> page pointer
    void add(const Slice& key, const PagePointer& ptr);
};
```

- **Value Index**: 存储每个 Data Page 的第一个 Key，用于按 key 值查找
- **Ordinal Index**: 存储每个 Data Page 的第一个 ordinal，用于按 row id 查找

### 2.5 Bloom Filter

为了快速判断某个 key 是否存在，Primary Key Index 还包含 Bloom Filter：

```cpp
// be/src/olap/primary_key_index.cpp
auto opt = segment_v2::BloomFilterOptions();
opt.fpp = 0.01;  // 误报率 1%
RETURN_IF_ERROR(segment_v2::PrimaryKeyBloomFilterIndexWriterImpl::create(
        opt, type_info, &_bloom_filter_index_builder));
```

## 3. 存储结构

### 3.1 文件内布局

Primary Key Index 存储在 **Segment 文件内部**：

```
Segment File Layout:
┌────────────────────────────────────────────────────────────────────┐
│                         Column Data                                 │
│  (各列的数据页)                                                      │
├────────────────────────────────────────────────────────────────────┤
│                      Primary Key Index                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Data Page 0 │ Data Page 1 │ ... │ Data Page N │              │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │  Index Page (if multiple data pages)                          │  │
│  ├──────────────────────────────────────────────────────────────┤  │
│  │  Bloom Filter Data                                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────┤
│                       Segment Footer                                │
│  (包含 PrimaryKeyIndexMetaPB)                                       │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 元数据结构

```protobuf
// gensrc/proto/segment_v2.proto
message PrimaryKeyIndexMetaPB {
    optional IndexedColumnMetaPB primary_key_index = 1;
    optional ColumnIndexMetaPB bloom_filter_index = 2;
    optional bytes min_key = 3;
    optional bytes max_key = 4;
}

message IndexedColumnMetaPB {
    optional int32 data_type = 1;
    optional int32 encoding = 2;
    optional int64 num_values = 3;
    optional BTreeMetaPB ordinal_index_meta = 4;
    optional BTreeMetaPB value_index_meta = 5;
    optional int32 compression = 6;
}
```

## 4. 查询流程

### 4.1 点查流程

```cpp
// be/src/olap/rowset/segment_v2/indexed_column_reader.cpp
Status IndexedColumnIterator::seek_at_or_after(const void* key, bool* exact_match) {
    // Step 1: 通过 Value Index 定位到目标 Data Page
    if (_reader->_has_index_page) {
        std::string encoded_key;
        _reader->_value_key_coder->full_encode_ascending(key, &encoded_key);
        Status st = _value_iter.seek_at_or_before(encoded_key);
        // ...
    }
    
    // Step 2: 读取 Data Page
    RETURN_IF_ERROR(_read_data_page(data_page_pp));
    
    // Step 3: 在 Data Page 内二分查找
    Status st = _data_page.data_decoder->seek_at_or_after_value(key, exact_match);
    // ...
}
```

### 4.2 完整查询示例

```
Query: SELECT * FROM table WHERE pk = 'key_xxx'

1. Bloom Filter 快速过滤
   ├── check_present('key_xxx') 
   └── 如果返回 false，直接跳过该 segment

2. Value Index 定位 Data Page
   ├── seek_at_or_before('key_xxx')
   └── 找到包含该 key 的 Data Page

3. Data Page 内查找
   ├── 读取并解压 Data Page
   ├── 二分查找定位 key
   └── 返回 row_id (ordinal)

4. 根据 row_id 读取行数据
```

## 5. 与 Short Key Index 的对比

| 特性 | Primary Key Index | Short Key Index |
|------|------------------|-----------------|
| **使用场景** | Unique Key MOW 表 | 所有表类型 |
| **粒度** | 行级 | 每 N 行 (默认 1024) |
| **索引内容** | 完整 Primary Key | 前缀 Key |
| **存储开销** | 较大 | 较小 |
| **查询能力** | 精确定位任意 key | 范围扫描 |
| **去重支持** | 支持 | 不支持 |

## 6. 相关配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `primary_key_data_page_size` | 32768 (32KB) | Data Page 大小 |
| `disable_pk_storage_page_cache` | false | 是否禁用 PK Index Page Cache |

## 7. 总结

1. **粒度**: Primary Key Index 是行级粒度，为每一行创建索引条目
2. **算法结构**: 采用 B-Tree + Data Page 的分层索引结构，类似 RocksDB Partitioned Index
3. **存储方式**: 
   - 使用 IndexedColumnWriter 将有序的 key 写入多个 Data Page
   - 通过 Value Index (B-Tree) 加速按 key 查找
   - 通过 Ordinal Index (B-Tree) 支持按 row id 查找
   - 附带 Bloom Filter 进行快速存在性判断
4. **压缩**: 使用 ZSTD 压缩
