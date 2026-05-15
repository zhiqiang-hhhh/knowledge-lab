```c++

InterpreterSelectQuery::InterpreterSelectQuery(
    const ASTPtr & query_ptr_,
    const ContextPtr & context_,
    const StoragePtr & storage_,
    ...
)
{
    ...

    if (storage)
    {
        table_lock = storage->lockForShare(context->getInitialQueryId(), context->getSettingsRef().lock_acquire_timeout);
        table_id = storage->getStorageID();
        if (!metadata_snapshot)
            metadata_snapshot = storage->getInMemoryMetadataPtr();

        storage_snapshot = storage->getStorageSnapshotForQuery(metadata_snapshot, query_ptr, context);
    }
    ...
}

class IStorage
{
    ...
public:
    /// Creates a storage snapshot from given metadata.
    virtual StorageSnapshotPtr getStorageSnapshot(const StorageMetadataPtr & metadata_snapshot, ContextPtr /*query_context*/) const
    {
        return std::make_shared<StorageSnapshot>(*this, metadata_snapshot);
    }

    /// Creates a storage snapshot from given metadata and columns, which are used in query.
    virtual StorageSnapshotPtr getStorageSnapshotForQuery(const StorageMetadataPtr & metadata_snapshot, const ASTPtr & /*query*/, ContextPtr query_context) const
    {
        return getStorageSnapshot(metadata_snapshot, query_context);
    }
}

struct StorageShapshot
{
    const IStorage & storage;
    const StorageMetadataPtr & metadata;
    const ColumnsDescription object_columns;
q
    using DataPtr = std::unique_ptr<Data>;
    DataPtr data;

    ...
}

StorageSnapshot(
        const IStorage & storage_,
        const StorageMetadataPtr & metadata_)
        : storage(storage_), metadata(metadata_)
{
    init();
}

void StorageSnapshot::init()
{
    for (const auto & [name, type] : storage.getVirtuals())
        virtual_columns[name] = type;
}

QueryPlanPtr MergeTreeDataSelectExecutor::read(
    ...
    const StorageSnapshotPtr & storage_snapshot,
    ...
)
{
    ...
    const auto & snapshot_data = assert_cast<const MergeTreeData::SnapshotData &>(*storage_snapshot->data);

    const auto & parts = snapshot_data.parts;
    
    auto plan = readFromParts(
        query_info.merge_tree_select_result_ptr ? MergeTreeData::DataPartsVector{} : parts,
        ...
        storage_snapshot,
        ...
    );
}
```
