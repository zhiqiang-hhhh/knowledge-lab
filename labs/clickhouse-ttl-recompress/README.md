# ClickHouse TTL recompress

给 MergeTree 表增加 `TTL ... RECOMPRESS CODEC(ZSTD)`。

**默认模式**：脚本默认执行 `--analysis` 模式，分析所有表的容量和存储类型，不做任何修改。

```bash
python3 -m pip install clickhouse-connect

# 默认模式：容量分析（区分纯 local、本地 volume MOVE 与 S3/remote MOVE）
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics

# 等同于显式指定 --analysis
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --analysis

# 计划模式：输出 SQL 但不执行（原 dry-run）
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --limit 20 \
  --plan

# 只读盘点已有 TTL RECOMPRESS、但未启用 materialize_ttl_recalculate_only 的表，并打印修复 SQL
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --repair-setting

# 确认盘点结果后执行 setting 修复；不会修改 TTL 规则
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --apply-repair

# 执行模式：应用 TTL RECOMPRESS 修改
python3 ttl_recompress.py \
  --host clickhouse.example.com \
  --databases analytics \
  --cluster production \
  --limit 20 \
  --apply
```

**模式说明**：
- **默认**（无参数）或 `--analysis`：容量分析，包含所有表（包括 system 库），只读不修改
- `--plan`：计划模式，输出 SQL 但不执行，受 `--limit` 限制（默认 20 张表）
- `--apply`：执行模式，应用 TTL RECOMPRESS 修改
- `--repair-setting`：盘点模式，检查需要修复 `materialize_ttl_recalculate_only` 的表
- `--apply-repair`：修复模式，执行 setting 修复

默认并行提交 ALTER，并行度为 10，可用 `--apply-concurrency` 覆盖。每张表会执行：

```sql
-- 仅当表未显式启用 materialize_ttl_recalculate_only 时执行
ALTER TABLE db.table ON CLUSTER production
    MODIFY SETTING
        materialize_ttl_recalculate_only = true;

ALTER TABLE db.table ON CLUSTER production
    MODIFY TTL
        <原有的完整 table TTL>,
        <partition_key> + INTERVAL <1 WEEK 或 1 DAY> RECOMPRESS CODEC(ZSTD)
    SETTINGS materialize_ttl_after_modify = 0;
```

默认情况下，`MODIFY TTL` 会追加 query-level `SETTINGS materialize_ttl_after_modify = 0`，避免自动对历史数据生成 `MATERIALIZE TTL` mutation。如果需要自动物化历史 TTL（不推荐用于生产环境），可使用 `--materialize-ttl-after-modify` 选项。

注意：

- **默认模式（`--analysis`）**：全量只读容量盘点，分析 `system.parts` 中所有 active tables，包括 `system` 库，不受 `--limit` 限制；如果显式传了 `--databases` 或 `--tables`，仍会按这些条件过滤。它读取每张表的 `storage_policy`，并结合 `system.storage_policies` 与 `system.disks.is_remote` 解析每条 TTL MOVE 的目标，将 eligible 表准确分为无 MOVE 的纯 local、本地 volume/disk MOVE、S3/remote MOVE；无法从当前拓扑解析的目标单独列为 `unresolved-move`，不会误算成 S3。parts 当前实际占用仍通过 `system.parts.disk_name -> system.disks.is_remote` 汇总为 local/remote bytes。输出中的 `total eligible local disk bytes` 是执行 RECOMPRESS 后可能被优化的本地数据规模，不是预计一定释放的空间；准确节省量取决于当前 codec、数据内容和 ZSTD 的实际压缩率，必须在 recompression 完成后测量。
- **计划模式（`--plan`）** 和 **执行模式（`--apply`）**：按 `system.parts` 的 `sum(bytes)` 降序选择前 `--limit 20` 张 active 表，并在日志开头输出 database、table、总行数和总 bytes。`--plan` 输出 SQL 计划但不执行，`--apply` 执行修改。
- **修复模式（`--repair-setting`）**：独立的只读修复盘点模式，扫描 `system.tables` 中所有非 system MergeTree 表（包括没有 active part 的空表），再按 `--metadata-batch-size` 分批读取建表语句，以避免大型集群一次读取全量 `create_table_query` 超时。它统计 table-level TTL 含 `RECOMPRESS` 的表、需要修复的表和已经启用 setting 的表，并为需要修复的表打印 `MODIFY SETTING materialize_ttl_recalculate_only = true`。该模式不受 `--limit`/`--all` 影响，但仍支持 `--databases`、`--tables` 和 `--cluster`。
- **修复执行模式（`--apply-repair`）**：先输出与 `--repair-setting` 相同的统计和 SQL，再执行修复；它只修改 `materialize_ttl_recalculate_only`，不会修改现有 TTL。未显式设置、设置为 `0` 或 `false` 都会被修复，显式设置为 `1` 或 `true` 的表会跳过。修复默认并发度同样为 10，可用 `--apply-concurrency` 调整。
- `--plan`、`--apply`、`--analysis`、`--repair-setting` 和 `--apply-repair` 是互斥模式。不指定任何模式时默认为 `--analysis`。
- `--plan` 和 `--apply` 保持安全默认：只处理非 system 库，并受 `--limit` 限制（默认 20 张表），除非显式传 `--all`。
- `--analysis` 分别输出 `Top eligible local-only tables`、`Top eligible local-volume-move tables`、`Top eligible S3/remote-move tables`，必要时还会输出 `unresolved-move`；这些表就是全量分析范围内按当前规则可处理的表，并逐表显示 local、remote 和 total bytes。
- `Top skipped tables by bytes` 会打印最多 20 张跳过的表和 skip reason。普通模式若当前 `--limit` 候选集中不足 20 张 skipped 表，脚本会额外扩大只读扫描范围用于补足 skipped 摘要；这不会改变 `--apply` 实际处理的 eligible 表范围。
- 每张候选表都会输出当前 partition key、当前 table TTL、计划应用的 setting 和完整 TTL；跳过时输出 skip reason。
- 如果表的 `materialize_ttl_recalculate_only = 1/true` 已经满足，脚本会跳过 setting ALTER，只执行 TTL ALTER；apply 日志会显示 `setting-skipped reason=already-satisfied`。
- stderr 进度日志明确标记 `stage=fetch`、`stage=plan` 和 `stage=apply`。fetch 会打印完整查询 SQL；apply 阶段会逐表打印 setting ALTER 和 TTL ALTER 的完整 SQL及其开始、完成状态。
- `MODIFY TTL` 替换的是完整 table-level TTL，因此脚本会保留已有 DELETE/GROUP BY TTL，而不是只写新的 RECOMPRESS rule。
- 没有 table-level DELETE TTL 的表会跳过，skip reason 为 `no table TTL DELETE`。`TTL time + INTERVAL 30 DAY` 这种 ClickHouse 隐式 DELETE TTL 会被视为 DELETE TTL；完全没有 `TTL` 子句，或只有 MOVE/GROUP BY/RECOMPRESS TTL 的表不会新增 RECOMPRESS。
- 带 `TTL ... TO VOLUME/DISK` 的表默认保留原 MOVE 规则，并追加 `<partition_key> + INTERVAL 1 DAY RECOMPRESS CODEC(ZSTD)`。
- 已有任意 `RECOMPRESS` rule 的表会跳过。
- 普通表的 RECOMPRESS 生效表达式为 `system.tables.partition_key + INTERVAL 1 WEEK`；已有 TTL MOVE 的表改为 `system.tables.partition_key + INTERVAL 1 DAY`。两者都不接受命令行表达式。
- 没有分区键的表会跳过。分区键必须是能够与 `INTERVAL 1 WEEK` 或 `INTERVAL 1 DAY` 相加的 Date/DateTime 表达式；Tuple 等复合分区键不适用。
- 脚本默认会在 `MODIFY TTL` 查询后追加 query-level `SETTINGS materialize_ttl_after_modify = 0`，让 `MODIFY TTL` 只修改 TTL 规则，不自动生成历史数据的 `MATERIALIZE TTL` mutation，避免历史 parts 被批量重写和重新压缩。如果需要自动物化历史 TTL（不推荐），可使用 `--materialize-ttl-after-modify` 选项。
- 使用 `--materialize-ttl-after-modify` 时，脚本会在提交新的 TTL ALTER 前检查全局 `system.mutations` 中未完成的 `MATERIALIZE TTL` 数量；达到 10 个时每 5 秒等待一次。对于带 TTL MOVE 的表，即使使用此选项也会强制添加 `materialize_ttl_after_modify = 0`，避免自动 materialize TTL 时读写历史 S3 数据。
- 对 ReplicatedMergeTree，如果所有 shard 上表结构一致，可使用 `ON CLUSTER`；否则应按 shard 分别执行。
