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