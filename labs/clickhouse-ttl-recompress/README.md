# ClickHouse TTL recompress

给 MergeTree 表增加 `TTL ... RECOMPRESS CODEC(ZSTD)`。脚本默认只输出 SQL，使用 `--apply` 才执行。

```bash
python3 -m pip install clickhouse-connect

python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics

# 检查 dry-run 输出后执行；多 shard 集群可指定 ON CLUSTER
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --cluster production \
  --apply
```

每张表严格按顺序执行：

```sql
ALTER TABLE db.table ON CLUSTER production
    MODIFY SETTING materialize_ttl_recalculate_only = true;

ALTER TABLE db.table ON CLUSTER production
    MODIFY TTL
        <原有的完整 table TTL>,
        <partition_key> + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD);
```

注意：

- `MODIFY TTL` 替换的是完整 table-level TTL，因此脚本会保留已有 DELETE/MOVE/GROUP BY TTL，而不是只写新的 RECOMPRESS rule。
- 已有任意 `RECOMPRESS` rule 的表会跳过。
- RECOMPRESS 生效表达式固定为 `system.tables.partition_key + INTERVAL 1 WEEK`，不再接受命令行表达式。
- 没有分区键的表会跳过。分区键必须是能够与 `INTERVAL 1 WEEK` 相加的 Date/DateTime 表达式；Tuple 等复合分区键不适用。
- `materialize_ttl_recalculate_only` 只影响后续 `MATERIALIZE TTL` 的行为；这两条 ALTER 本身不会立即把历史 parts 全部重压缩。历史数据需要重算 TTL metadata 时，再单独、限流执行 `ALTER TABLE ... MATERIALIZE TTL`。
- 对 ReplicatedMergeTree，如果所有 shard 上表结构一致，可使用 `ON CLUSTER`；否则应按 shard 分别执行。
