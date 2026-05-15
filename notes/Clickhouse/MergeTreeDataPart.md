# MergeTreeDataPart

```plantuml
class IMergeTreeDataPart
{
    + name : String
    + info : MergeTreePartInfo
    + uuid : UUID
    + index_granularity_info : MergeTreeIndexGranularityInfo
    + rows_count : size_t
    + modification_time : time_t
    + index : Index
    + partition : MergeTreePartition
    + index_granularity : MergeTreeIndexGranularity
    + minmax_idx : MinMaxIndex
    + checksums : Checksums
    + expired_columns : NameSet
    + default_codec : CompressionCodecPtr

    # loadUUID() : void
    # loadColumns() : void
    # loadChecksums() : void
    # loadIndexGranularity() : void
    # loadIndex() : void

}
```


* MergeTreeIndexGranularity

```c++
struct MergeTreeIndexGranularityInfo
{
public:
    /// Marks file extension '.mrk' or '.mrk2'
    String marks_file_extension;

    /// Is stride in rows between marks non fixed?
    bool is_adaptive = false;

    /// Fixed size in rows of one granule if index_granularity_bytes is zero
    size_t fixed_index_granularity = 0;

    /// Approximate bytes size of one granule
    size_t index_granularity_bytes = 0;

    MergeTreeIndexGranularityInfo(const MergeTreeData & storage, MergeTreeDataPartType type_);

    void changeGranularityIfRequired(const DataPartStoragePtr & data_part_storage);

    String getMarksFilePath(const String & path_prefix) const
    {
        return path_prefix + marks_file_extension;
    }

    size_t getMarkSizeInBytes(size_t columns_num = 1) const;

    static std::optional<std::string> getMarksExtensionFromFilesystem(const DataPartStoragePtr & data_part_storage);

private:
    MergeTreeDataPartType type;
    void setAdaptive(size_t index_granularity_bytes_);
    void setNonAdaptive();
}
```

Meta information about index granularity. 保存在 part directory/data.mrk 或者 part directory/data.mrk2 文件中。