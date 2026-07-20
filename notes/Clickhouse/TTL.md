# TTL

```plantuml
class StorageInMemoryMetadata
{
    ...
    + table_ttl : TTLTableDescription
}

StorageInMemoryMetadata *--  TTLTableDescription 

class TTLTableDescription 
{
    + definition_ast : ASTPtr
    + rows_ttl : TTLDescription
    ...
}

TTLTableDescription *-- TTLDescription

class TTLDescription
{
    + mode : TTLMode
    + expression_ast : ASTPtr
    ...
}

class MergeTreeDataPartTTLInfo
{
    + min : time_t
    + max : time_t
}

MergeTreeDataPartTTLInfos *-- MergeTreeDataPartTTLInfo

class MergeTreeDataPartTTLInfos
{
    + columns_ttl : TTLInfoMap
    + table_ttl : MergeTreeDataPartTTLInfo
    + part_min_ttl : time_t
    + part_max_ttl : time_t
    ...
}

IMergeTreeDataPart *-- MergeTreeDataPartTTLInfos

class IMergeTreeDataPart 
{
    + ttl_infos : MergeTreeDataPartTTLInfos
}
```

```c++
struct MergeTreeDataPartTTLInfo
{
    time_t min = 0;
    time_t max = 0;

    void update(time_t time)
    {
        if (time && (!min))
    }
}


MergedBlockOutputStream::finalizePartOnDisk(new_part, checksums)
{
    ...
    if (!new_part->ttl_infos.empty())
    {
        /// Write a file with ttl infos in json format
        auto out = volume->getDisk()->writeFile(fs::path(part_path) / "ttl.txt", 4096);
        HashingWriteBuffer out_hashing(*out);
        new_part->ttl_infos.write(out_hashing);
        checksums.files["ttl.txt"].file_size = out_hashing.count();
        checksums.files["ttl.txt"].file_hash = out_hashing.getHash();
        out->preFinalize();
        written_files.emplace_back(std::move(out));
    }
}
```

### ColumnDepency

```cpp
ColumnDependency(const String & column_name_, Kind kind_)
        : column_name(column_name_), kind(kind_) {}
```
描述 column_name_ 是某个其他XXX的依赖。XXX 就是 Kind 这个 enum 里面区分的类型：
```cpp
enum Kind : UInt8
{
    /// Exists any skip index, that requires @column_name
    SKIP_INDEX,

    /// Exists any projection, that requires @column_name
    PROJECTION,

    /// Exists any TTL expression, that requires @column_name
    TTL_EXPRESSION,

    /// TTL is set for @column_name.
    TTL_TARGET,

    /// Exists any statistics, that requires @column_name
    STATISTICS,
};
```
注释很清楚了。

ColumnDependency 与 TTL 的关系：

TTL 依赖某个表达式来决定某行/某个part是否“过期“。当判断某个 TTL 条件是否满足的时候，我们需要去读对应的列，后续还可能需要去更新某些列，因此需要用 `ColumnDepencency` 来记录和描述上述信息。

### void MutationsInterpreter::prepare(bool dry_run)