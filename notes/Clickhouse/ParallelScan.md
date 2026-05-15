```plantuml
class MergeTreeReadTask {
    /// Shared information required for reading.
    - MergeTreeReadTaskInfoPtr info;

    /// Readers for data_part of this task.
    /// May be reused and released to the next task.
    - Readers readers;

    /// Range readers to read mark_ranges from data_part
    - RangeReaders range_readers;

    /// Ranges to read from data_part
    - MarkRanges mark_ranges;

    /// Used to satistfy preferred_block_size_bytes limitation
    - MergeTreeBlockSizePredictorPtr size_predictor;
    
    + BlockAndProgress read(const BlockSizeParams & params);

    + {static} Readers createReaders(const MergeTreeReadTaskInfoPtr &, const Extras &, const MarkRanges &);
    + {static} RangeReaders createRangeReaders(const Readers &, const PrewhereExprInfo &);
}

class MergeTreeReadTaskInfo
{
    /// Data part which should be read while performing this task
    - DataPartPtr data_part;
    /// Parent part of the projection part
    - DataPartPtr parent_part;
    /// For `part_index` virtual column
    - size_t part_index_in_query;
    /// Alter converversionss that should be applied on-fly for part.
    - AlterConversionsPtr alter_conversions;
    /// Column names to read during PREWHERE and WHERE
    - MergeTreeReadTaskColumns task_columns;
    /// Shared initialized size predictor. It is copied for each new task.
    - MergeTreeBlockSizePredictorPtr shared_size_predictor;
    /// Shared constant fields for virtual columns.
    - VirtualFields const_virtual_fields;
    /// The amount of data to read per task based on size of the queried columns.
    - size_t min_marks_per_task = 0;
}

MergeTreeReadTask *-- MergeTreeReadTaskInfo

class MergeTreeReadPoolBase {
    MergeTreeReadTaskPtr createTask(MergeTreeReadTaskInfoPtr, MarkRanges, MergeTreeReadTask * previous_task);
}


MergeTreeReadPoolBase -up-> IMergeTreeReadPool
MergeTreeReadPool -up-> MergeTreeReadPoolBase

class MergeTreeReadPool {

}


class IMergeTreeSelectAlgorithm {
    {abstract} MergeTreeReadTaskPtr getNewTask(IMergeTreeReadPool & pool, MergeTreeReadTask * previous_task) = 0;
    {abstract} BlockAndProgress readFromTask(MergeTreeReadTask & task, const BlockSizeParams & params) = 0;
}

class MergeTreeSelectProcessor {
    - MergeTreeReadPoolPtr pool_,
    - MergeTreeSelectAlgorithmPtr algorithm_
    /// Current task to read from.
    - MergeTreeReadTaskPtr task
}


MergeTreeSelectProcessor *-- IMergeTreeReadPool
MergeTreeSelectProcessor *-- IMergeTreeSelectAlgorithm

MergeTreeSelectProcessor *-- MergeTreeReadTask
```



```cpp
ChunkAndProgress MergeTreeSelectProcessor::read()
{
    while (!is_cancelled)
    {
        if (!task || algorithm->needNewTask(*task))
            task = algorithm->getNewTask(*pool, task.get());

        if (!task)
            break;

        ...

        if (!task->getMainRangeReader().isInitialized())
            initializeRangeReaders();

        auto res = algorithm->readFromTask(*task, block_size_params);

        if (res.row_count)
        {
            /// Reorder the columns according to result_header
            Columns ordered_columns;
            ordered_columns.reserve(result_header.columns());
            for (size_t i = 0; i < result_header.columns(); ++i)
            {
                auto name = result_header.getByPosition(i).name;
                ordered_columns.push_back(res.block.getByName(name).column);
            }

            auto chunk = Chunk(ordered_columns, res.row_count);
            if (add_part_level)
                chunk.getChunkInfos().add(std::make_shared<MergeTreePartLevelInfo>(task->getInfo().data_part->info.level));

            return ChunkAndProgress{
                .chunk = std::move(chunk),
                .num_read_rows = res.num_read_rows,
                .num_read_bytes = res.num_read_bytes,
                .is_finished = false};
        }

        return {Chunk(), res.num_read_rows, res.num_read_bytes, false};
    }

    return {Chunk(), 0, 0, true};
}
```


```cpp
IAsynchronousReader & Context::getThreadPoolReader(FilesystemReaderType type) const
{
    callOnce(shared->readers_initialized, [&] {
        const auto & config = getConfigRef();
        shared->asynchronous_remote_fs_reader = createThreadPoolReader(FilesystemReaderType::ASYNCHRONOUS_REMOTE_FS_READER, config);
        shared->asynchronous_local_fs_reader = createThreadPoolReader(FilesystemReaderType::ASYNCHRONOUS_LOCAL_FS_READER, config);
        shared->synchronous_local_fs_reader = createThreadPoolReader(FilesystemReaderType::SYNCHRONOUS_LOCAL_FS_READER, config);
    });

    switch (type)
    {
        case FilesystemReaderType::ASYNCHRONOUS_REMOTE_FS_READER:
            return *shared->asynchronous_remote_fs_reader;
        case FilesystemReaderType::ASYNCHRONOUS_LOCAL_FS_READER:
            return *shared->asynchronous_local_fs_reader;
        case FilesystemReaderType::SYNCHRONOUS_LOCAL_FS_READER:
            return *shared->synchronous_local_fs_reader;
    }
}
```

对于每个 part 都会去计算，每次读需要读多少个 Mark
```cpp
MergeTreeReadPoolBase::MergeTreeReadPoolBase(...) {
    fillPerPartInfos(settings);
}

void MergeTreeReadPoolBase::fillPerPartInfos(const Settings & settings)
{
    for (const auto & part_with_ranges : parts_ranges)
    {
        MergeTreeReadTaskInfo read_task_info;
        ...

        read_task_info.min_marks_per_task
            = calculateMinMarksPerTask(part_with_ranges, column_names, prewhere_info, pool_settings, settings);
        ...
        per_part_infos.push_back(std::make_shared<MergeTreeReadTaskInfo>(std::move(read_task_info)));
    }
}
```


`ReadFromMergeTree::AnalysisResultPtr ReadFromMergeTree::selectRangesToRead(`




```cpp
/// Reads the data between pairs of marks in the same part. When reading consecutive ranges, avoids unnecessary seeks.
/// When ranges are almost consecutive, seeks are fast because they are performed inside the buffer.
/// Avoids loading the marks file if it is not needed (e.g. when reading the whole part).
class IMergeTreeReader : private boost::noncopyable
{

}



MergeTreeRangeReader::ReadResult MergeTreeRangeReader::read(size_t max_rows, MarkRanges & ranges)
{

}
```


这个函数是在不同的 stream 之间分配 mark range 的
spreadMarkRangesAmongStreams

```plantuml
MergeTreeReaderWide -up-> IMergeTreeReader
MergeTreeReaderWide *-- MergeTreeReaderStream

class MergeTreeReaderWide {
    - uncompressed_cache* : UncompressedCache
}
```