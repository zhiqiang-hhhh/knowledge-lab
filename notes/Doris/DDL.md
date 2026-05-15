### Create table

```java
public class InternalCatalog {
    public boolean createTable(CreateTableStmt stmt) throws UserException {
        ...
        return createOlapTable(Database db, CreateTableStmt stmt);
    }

    private boolean createOlapTable(Database db, CreateTableStmt stmt) throws UserException {
        ...
        // set base index meta
        olapTable.setIndexMeta(baseIndexId, tableName, baseSchema, schemaVersion, schemaHash, shortKeyColumnCount,
                baseIndexStorageType, keysType, olapTable.getIndexes());
        ...
    }
}
```
What is base index:
* doris 默认自带主键索引

所以这里的 base index 指的就是主键索引


doris 的表结构分为两层，第一层是 partition 分区，第二层是 tablet 分桶。
因此建表的时候的逻辑是先创建分区，然后在创建分桶，创建副本。

对于 tablet 的每一个副本发起一个 thrift rpc 请求。
```java
createPartitionWithIndices {
    ...
    for (Tablet tablet : index.getTablets()) {
        for (Replica replica : tablet.getReplicas()) {
            CreateReplicaTask task = new CreateReplicaTask(backendId...);
        }
    }
}
```
BE 上收到如下的请求：
```thrift
struct TCreateTabletReq {
    1: required Types.TTabletId tablet_id
    2: required TTabletSchema tablet_schema
    3: optional Types.TVersion version
    // Deprecated
    4: optional Types.TVersionHash version_hash 
    5: optional Types.TStorageMedium storage_medium
    6: optional bool in_restore_mode
    // this new tablet should be colocate with base tablet
    7: optional Types.TTabletId base_tablet_id
    8: optional Types.TSchemaHash base_schema_hash
    9: optional i64 table_id
    10: optional i64 partition_id
    // used to find the primary replica among tablet's replicas
    // replica with the largest term is primary replica
    11: optional i64 allocation_term
    // indicate whether this tablet is a compute storage split mode, we call it "eco mode"
    12: optional bool is_eco_mode
    13: optional TStorageFormat storage_format
    14: optional TTabletType tablet_type
    // 15: optional TStorageParam storage_param
    16: optional TCompressionType compression_type = TCompressionType.LZ4F
    17: optional Types.TReplicaId replica_id = 0
    // 18: optional string storage_policy
    19: optional bool enable_unique_key_merge_on_write = false
    20: optional i64 storage_policy_id
    21: optional TBinlogConfig binlog_config
    22: optional string compaction_policy = "size_based"
    23: optional i64 time_series_compaction_goal_size_mbytes = 1024
    24: optional i64 time_series_compaction_file_count_threshold = 2000
    25: optional i64 time_series_compaction_time_threshold_seconds = 3600
    26: optional i64 time_series_compaction_empty_rowsets_threshold = 5
    27: optional i64 time_series_compaction_level_threshold = 1
    28: optional TInvertedIndexStorageFormat inverted_index_storage_format = TInvertedIndexStorageFormat.DEFAULT // Deprecated
    29: optional Types.TInvertedIndexFileStorageFormat inverted_index_file_storage_format = Types.TInvertedIndexFileStorageFormat.V2

    // For cloud
    1000: optional bool is_in_memory = false
    1001: optional bool is_persistent = false
}
```
在 `TabletManager::_create_tablet_meta_and_dir_unlocked` 完成两个关键步骤：
1. 创建 TabletMeta
2. 在磁盘上创建 tablet 的目录(`shardId/tabletId/schemaHash`)

之后的步骤：
3. 把 tablet meta 添加到 tablet maneger 里
4. 把 tablet meta 持久化


### Schema Change

对于 LightSchemaChange，只改 FE 的 meta，不会直接改 BE 内存的 meta。
BE 内存的 meta 会等到下一次导入时进行更新。
在 BE 内存 meta 与 FE meta 不同的期间，查询将会使用 Plan 中的 TabletSchema 来规划 Block 的结构。


```java
class SchemaChangeHander {
    private void createJob(String rawSql, long dbId, OlapTable olapTable, Map<Long, LinkedList<Column>> indexSchemaMap,
                           Map<String, String> propertyMap, List<Index> indexes,
                           boolean isBuildIndex) throws UserException {
        ...
        olapTable.setState(OlapTableState.SCHEMA_CHANGE);
        // 2. add schemaChangeJob
        addAlterJobV2(schemaChangeJob);
        // 3. write edit log
        Env.getCurrentEnv().getEditLog().logAlterJob(schemaChangeJob);
    }


    private boolean processModifyColumn(ModifyColumnClause alterClause, OlapTable olapTable,
                                        Map<Long, LinkedList<Column>> indexSchemaMap) throws DdlException {
        if (lightSchemaChange) {
            ...
        } else {
            createJob(rawSql, db.getId(), olapTable, indexSchemaMap, propertyMap, newIndexes, false);
        }
    }
}    
```

```cpp
SchemaChangeJob::SchemaChangeJob(StorageEngine& local_storage_engine,
                                 const TAlterTabletReqV2& request, const std::string& job_id)
        : _local_storage_engine(local_storage_engine) {
    _base_tablet = _local_storage_engine.tablet_manager()->get_tablet(request.base_tablet_id);
    _new_tablet = _local_storage_engine.tablet_manager()->get_tablet(request.new_tablet_id);
    if (_base_tablet && _new_tablet) {
        _base_tablet_schema = std::make_shared<TabletSchema>();
        _base_tablet_schema->update_tablet_columns(*_base_tablet->tablet_schema(), request.columns);
        // The request only include column info, do not include bitmap or bloomfilter index info,
        // So we also need to copy index info from the real base tablet
        _base_tablet_schema->update_index_info_from(*_base_tablet->tablet_schema());
        // During a schema change, the extracted columns of a variant should not be included in the tablet schema.
        // This is because the schema change for a variant needs to ignore the extracted columns.
        // Otherwise, the schema types in different rowsets might be inconsistent. When performing a schema change,
        // the complete variant is constructed by reading all the sub-columns of the variant.
        _new_tablet_schema = _new_tablet->tablet_schema()->copy_without_variant_extracted_columns();
    }
    _job_id = job_id;
}
```