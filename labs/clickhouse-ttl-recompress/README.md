# ClickHouse TTL Recompress Planner

这个工具目录用于给已有 `MergeTree` 表规划和执行 table-level `TTL ... RECOMPRESS CODEC(...)`。脚本使用 Python package `clickhouse-connect` 连接 `ClickHouse` HTTP interface，不调用系统 `clickhouse` binary。

## 目标

对现有表补充或重建 table-level `TTL RECOMPRESS`，把冷分区重压缩为更高压缩率的 codec，同时保持已有 delete-only table-level `TTL` 不变。

默认策略：

- codec: `ZSTD(4)`
- 周分区热窗口：`<partition_key> + INTERVAL 1 WEEK`
- 天分区热窗口：`<partition_key> + INTERVAL 2 DAY`

## 执行模型

脚本把流程拆成几个显式模式：

1. `plan`
   默认模式。只扫描表、打印 batch 计划和 skip report，不执行写操作。

2. `apply-ttl`
   先提交 replicated setting `ALTER`，让后续 TTL materialize 只重算 TTL metadata：

   ```sql
   ALTER TABLE db.table
   MODIFY SETTING materialize_ttl_recalculate_only = true;
   ```

   然后提交 replicated TTL metadata `ALTER`：

   ```sql
   ALTER TABLE db.table MODIFY TTL
       <recompress_expr> RECOMPRESS CODEC(ZSTD(4)),
       <existing_delete_ttl>;
   ```

   `MODIFY TTL` 是 replicated metadata `ALTER`。对同一个 `ReplicatedMergeTree` replica group 只执行一次，其他 active replicas 通过 replication log 自动应用。脚本不会做 cluster fanout，也不会对同一个 replica group 的每个 replica 分别写入。

   对没有 table-level `TTL` 的表，脚本会写入只包含一条 `RECOMPRESS` 规则的新 `TTL`。

3. `optimize`
   对所有表做完 `apply-ttl` 后，从 `system.parts` 找出 active parts 里磁盘占用最大的分区/codec 组合：

   ```sql
   SELECT
       database,
       `table`,
       partition,
       default_compression_codec,
       sum(bytes) AS bys
   FROM system.parts
   WHERE database NOT IN ('system')
   GROUP BY
       database,
       `table`,
       default_compression_codec,
       partition
   ORDER BY bys DESC
   LIMIT 20;
   ```

   脚本实际查询时会额外取 `partition_id`，并生成：

   ```sql
   OPTIMIZE TABLE db.table PARTITION ID '<partition_id>' FINAL;
   ```

4. `materialize`
   单独提交当前 batch 的 `MATERIALIZE TTL` mutation：

   ```sql
   ALTER TABLE db.table MATERIALIZE TTL SETTINGS mutations_sync = 0;
   ```

   这个阶段只选择当前 table-level `TTL` 已经包含 `RECOMPRESS` 的表。
   默认 `--mutations-sync 0` 只异步提交 mutation；如果需要等待完成，使用 `--wait-materialize` 让脚本轮询 `system.mutations`。
   不建议默认使用 `--mutations-sync 1` 做 server-side 长等待，因为 HTTP 客户端或中间层连接超时/断开时，`ClickHouse` 可能在 mutation 已经创建甚至完成后把这条 HTTP query 记录为 `QUERY_WAS_CANCELLED`。

   提交新的 `MATERIALIZE TTL` 前，脚本会用 `system.parts` 做 per-table precheck：

   - 没有 active parts 的表会跳过。
   - 如果任意 active part 的 `default_compression_codec` 已经等于当前 `TTL RECOMPRESS` 里的目标 codec，会跳过。这表示历史上已经触发过、触发后部分完成、或当前已有相关 mutation 在推进；重复提交成本过高，所以采用保守策略。
   - 只有在没有目标 codec active parts 时，才继续检查已经到期的 recompression TTL parts，即 `recompression_ttl_info.max <= now()` 的 active parts。
   - 如果 active non-target parts 缺少 `recompression_ttl_info`，脚本不会跳过，因为这通常表示新增 TTL 元数据后老 parts 还没有被 `MATERIALIZE TTL` 重新计算过。

5. `resume-materialize`
   不提交新的 mutation，只从 `system.mutations` 查询未完成的 `MATERIALIZE TTL` mutation 并继续观察。

## 选择规则

扫描范围固定是 `engine LIKE '%MergeTree%'`，同时默认排除这些 database：

- `system`
- `INFORMATION_SCHEMA`
- `information_schema`

在此基础上，仍然支持：

- `--dbs`
- `--dbs-exclude`
- `--tables`

`--tables` 支持不带库名的 `table1,table2`，也支持带库名的 `db1.table1,db2.table2`。

## TTL 规划规则

`MODIFY TTL` 会覆盖表上完整的 table-level `TTL` 定义，所以脚本只处理这两类表：

1. 没有 table-level `TTL`
   直接生成一条新的 `RECOMPRESS` 规则。

2. 已有 table-level `TTL`，并且所有 entry 都是 delete-only 语义
   保留这些 entry 原样不动，并在最前面插入新的 `RECOMPRESS` entry。

脚本会跳过下列情况：

- 已有 `RECOMPRESS`
- 已有 `TO VOLUME`
- 已有 `TO DISK`
- 已有 `GROUP BY`
- 已有 `DELETE WHERE`
- table-level `TTL` 为空
- 分区表达式无法识别为天/周粒度

skip 原因会写到 `ttl_recompress_skipped.tsv`。

## 分区推断

脚本直接复用原始 `partition_key` 作为 `TTL RECOMPRESS` 表达式前缀，不改写表达式本身。只根据分区粒度追加 `INTERVAL`：

- 周分区：识别 `toStartOfWeek(...)` 或 `toMonday(...)`，生成 `<partition_key> + INTERVAL <weekly_hot_weeks> WEEK`
- 天分区：识别 `toDate(...)` 或 `toStartOfDay(...)`，生成 `<partition_key> + INTERVAL <daily_hot_days> DAY`

默认值：

- `--weekly-hot-weeks 1`
- `--daily-hot-days 2`

## Batch 与输出

脚本不会在 SQL 里使用 `LIMIT` 或 `OFFSET`，而是在 Python 内部排序后切 batch。默认 `--batch-size 10`，支持 `--batch` 和 `--all-batches`。

dry-run 输出会展示：

- 当前 table-level `TTL` 分类
- 当前 `TTL RECOMPRESS`
- 当前 delete `TTL`
- 新生成的 `TTL RECOMPRESS`
- 完整的新 `TTL`
- 将要提交的 replicated `MODIFY SETTING materialize_ttl_recalculate_only = true` statement
- 将要提交的 replicated `MODIFY TTL` statement

输出文件位于 `--output-dir`：

- `ttl_recompress.log`
- `ttl_recompress_skipped.tsv`
