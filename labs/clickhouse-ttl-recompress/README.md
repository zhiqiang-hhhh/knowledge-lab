# ClickHouse TTL Recompress Planner

这个工具目录用于给已有 `MergeTree` 表规划和执行 table-level `TTL ... RECOMPRESS CODEC(...)`。脚本使用 Python package `clickhouse-connect` 连接 `ClickHouse` HTTP interface，不调用系统 `clickhouse` binary。

## 目标

对现有表补充或重建 table-level `TTL RECOMPRESS`，把冷分区重压缩为更高压缩率的 codec，同时保持已有 delete-only table-level `TTL` 不变。

默认策略：

- codec: `ZSTD(4)`
- 周分区热窗口：`<partition_key> + INTERVAL 1 WEEK`
- 天分区热窗口：`<partition_key> + INTERVAL 2 DAY`

## 执行模型

脚本把流程拆成四个显式模式：

1. `plan`
   默认模式。只扫描表、打印 batch 计划和 skip report，不执行写操作。

2. `apply-ttl`
   提交 replicated metadata `ALTER`：

   ```sql
   ALTER TABLE db.table MODIFY TTL
       <recompress_expr> RECOMPRESS CODEC(ZSTD(4)),
       <existing_delete_ttl>
   SETTINGS materialize_ttl_after_modify = 0;
   ```

   `MODIFY TTL` 是 replicated metadata `ALTER`。对同一个 `ReplicatedMergeTree` replica group 只执行一次，其他 active replicas 通过 replication log 自动应用。脚本不会做 cluster fanout，也不会对同一个 replica group 的每个 replica 分别写入。

   对没有 table-level `TTL` 的表，脚本会写入只包含一条 `RECOMPRESS` 规则的新 `TTL`。

3. `materialize`
   单独提交当前 batch 的 `MATERIALIZE TTL` mutation：

   ```sql
   ALTER TABLE db.table MATERIALIZE TTL SETTINGS mutations_sync = 1;
   ```

   这个阶段只选择当前 table-level `TTL` 已经包含 `RECOMPRESS` 的表。

4. `resume-materialize`
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
- 将要提交的 replicated `MODIFY TTL` statement

输出文件位于 `--output-dir`：

- `ttl_recompress.log`
- `ttl_recompress_skipped.tsv`
