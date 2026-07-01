# ClickHouse S3 TTL Tiering Lab

这个实验目录用于生成并执行 `ClickHouse` 表从本地热数据到 `S3` 冷数据的 `TTL` 分层迁移计划。脚本使用 Python package `clickhouse-connect` 连接 `ClickHouse` HTTP interface，不调用系统 `clickhouse` binary。

## 目标

在用户无感的情况下，用 `S3` 作为冷数据底层存储，降低本地盘成本。实验方案不把新写入数据直接写入 `S3`，而是让新数据继续写入本地热 volume；超过热数据窗口后，通过 `TTL MOVE` 和 `TTL RECOMPRESS` 把冷数据移动到 `cold` volume。

## 三阶段执行模型

脚本把迁移拆成三个阶段：

1. `plan`
   默认模式，只扫描表、打印当前 batch 的 `ALTER` 计划和 skip report，不执行写操作。脚本不持久化 `ALTER` plan，每次运行都从 `system.tables` 当前状态重新计算。

2. `alter`
   通过 `--execute-alter` 执行当前 batch 的 metadata 变更：

   ```sql
   ALTER TABLE db.table MODIFY SETTING storage_policy = 's3_tier';

   ALTER TABLE db.table MODIFY TTL
       <move_expr> TO VOLUME 'cold',
       <move_expr> RECOMPRESS CODEC(ZSTD(12)),
       <existing_delete_ttl>
   SETTINGS materialize_ttl_after_modify = 0;
   ```

   这一步不会触发历史数据搬迁。

3. `materialize`
   通过 `--execute-materialize` 单独提交当前 batch 的 `MATERIALIZE TTL` mutation。默认使用 `mutations_sync = 0`，只提交后台任务，不同步等待。

   ```sql
   ALTER TABLE db.table MATERIALIZE TTL SETTINGS mutations_sync = 0;
   ```

`MATERIALIZE TTL` 阶段也是无状态的：脚本重新扫描当前表状态，只选择已经使用目标 `storage_policy`，并且当前 `TTL` 里已经包含 `TO VOLUME 'cold'` 和 `RECOMPRESS` 的表。`--resume-materialize` 不读取本地 state file，而是直接从 `system.mutations` 查询未完成的 `MATERIALIZE TTL` mutation。

## TTL 保护规则

`MODIFY TTL` 会覆盖表上完整的 `TTL` 定义，因此脚本必须把已有的删除规则带回新的 `TTL` 定义里。脚本只接受已有 table-level `TTL` 全部是 delete 语义的表；如果发现已有 `TTL` 包含下面任一操作，就跳过该表，并在 `s3_ttl_tiering_skipped.tsv` 里记录原因：

- `TO VOLUME`
- `TO DISK`
- `RECOMPRESS`
- `GROUP BY`
- `DELETE WHERE`

没有 table-level `TTL`、分区表达式无法识别为天/周粒度、或者目标 policy 与当前 policy 不兼容的表也会被跳过。

## 分区对齐

`TTL MOVE` 和 `TTL RECOMPRESS` 的表达式直接复用表的 `partition_key`，只根据分区粒度决定追加的 `INTERVAL`：

- 周分区：识别 `toStartOfWeek` 或 `toMonday`，生成 `<partition_key> + INTERVAL 2 WEEK`。
- 天分区：识别 `toDate` 或 `toStartOfDay`，生成 `<partition_key> + INTERVAL 8 DAY`。

周分区使用 `INTERVAL 2 WEEK` 是为了保证周一查询上周日数据时，上周日数据仍然在本地热层。如果使用 `INTERVAL 1 WEEK`，周日数据在下周一零点就满足 `TTL MOVE` 条件。

天分区默认使用 `8 DAY`，目的是保守覆盖最近 `7 * 24h` 的查询窗口。

脚本不会把 `toMonday` 改写成 `toStartOfWeek`，因为 `toStartOfWeek` 默认以星期日作为一周开始，和 `toMonday` 的星期一边界不一致。直接复用 `partition_key` 可以保证冷分层 TTL 和分区边界完全对齐。

对已经执行过旧版本脚本、当前 `TTL` 里已经有冷分层 `TO VOLUME` / `RECOMPRESS` 的表，可以显式使用修复模式重写 TTL。修复模式只处理已经使用目标 `storage_policy` 的表，并保留原有 delete TTL：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --dbs target_db \
  --repair-existing-tiering-ttl \
  --execute-alter \
  --all-batches
```

## Batch 语义

`--dbs` 非必填，默认扫描所有非系统库。`--dbs-exclude` 可以显式排除库。脚本不会在 SQL 里使用 `LIMIT` 或 `OFFSET`，而是在 Python 内部对候选表排序并切 batch。

默认 batch size 是 `10`。脚本会在扫描完成后打印汇总：需要处理的 database 数、table 数、总行数、总 size，以及按 database 总 size 降序排序的处理顺序。batch 也按 database 总 size 降序选择表，同一个 database 内按表名排序：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --batch 0 \
  --batch-size 10
```

默认只处理当前 batch。要一次性处理全部 planned tables，需要显式加 `--all-batches`：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --dbs target_db \
  --execute-alter \
  --all-batches
```

默认每处理 `100` 张候选表会向 stderr 打印一次进度日志，并追加写入当前目录的 `s3_ttl_tiering.log`。可以调小排查卡住的位置：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --log-every 10
```

使用 `--quiet` 可以关闭进度日志。

## 命令示例

安装依赖：

```bash
python3 -m pip install clickhouse-connect
```

生成计划：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --dbs target_db \
  --target-policy s3_tier \
  --cold-volume cold \
  --output-dir .
```

执行当前 batch 的 `ALTER`：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --dbs target_db \
  --target-policy s3_tier \
  --cold-volume cold \
  --output-dir . \
  --execute-alter
```

提交当前 batch 的 `MATERIALIZE TTL`，不等待完成：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --target-policy s3_tier \
  --cold-volume cold \
  --output-dir . \
  --execute-materialize \
  --mutations-sync 0
```

`MATERIALIZE TTL` 提交默认是串行限流的：`--max-pending-materialize 1`。脚本提交下一张表之前，会等待当前匹配范围内未完成的 `MATERIALIZE TTL` mutation 数量低于该阈值，避免一次性塞入过多后台任务。需要提高并发时显式调大：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --target-policy s3_tier \
  --cold-volume cold \
  --execute-materialize \
  --max-pending-materialize 3
```

提交并轮询等待，超时后只记录状态，不重试、不 kill mutation：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --target-policy s3_tier \
  --cold-volume cold \
  --output-dir . \
  --execute-materialize \
  --mutations-sync 0 \
  --wait-materialize \
  --materialize-timeout-seconds 3600
```

继续轮询之前提交过的 mutation：

```bash
python3 plan_s3_ttl_tiering.py \
  --host 127.0.0.1 \
  --http-port 8123 \
  --output-dir . \
  --resume-materialize \
  --wait-materialize
```

## 输出文件

脚本保持无状态，不持久化 `ALTER` plan 或 `MATERIALIZE TTL` state。脚本只在 `--output-dir` 下写入运行日志和 skip report：

- `s3_ttl_tiering.log`：运行进度日志。
- `s3_ttl_tiering_skipped.tsv`：跳过表和原因。

`MATERIALIZE TTL` 状态包括：

- `queued`：mutation 已提交，还没完成。
- `done`：`system.mutations.is_done = 1`。
- `failed`：`latest_fail_reason` 非空。
- `timeout`：脚本等待超过 `--materialize-timeout-seconds`，后台 mutation 可能仍在继续。
- `unknown`：脚本无法从 `system.mutations` 确认 mutation 状态。

## ReplicatedMergeTree 约束

对 `ReplicatedMergeTree`，不要在两个 replica 上都执行同一批 `ALTER` 或 `MATERIALIZE TTL`。metadata `ALTER` 和 mutation 都会进入 replication log；在一个 replica 提交后，其他 replica 会自动 apply。

如果两个 replica 都提交同一个 `MATERIALIZE TTL`，会产生两个独立 mutation，增加 mutation queue、后台 IO 和对象存储请求。脚本只连接一个目标 `ClickHouse` 节点，不使用 `clusterAllReplicas` 执行写操作。

## 本地验证结果

本地验证使用已有 `ClickHouse` node1 和 MinIO：

- `ClickHouse` HTTP port：`18101`
- MinIO endpoint：`http://127.0.0.1:19900/clickhouse/bench/`
- 测试 policy：`ttl_demo`
- cold volume：`cold`

测试表覆盖了周分区纯 delete `TTL`、天分区纯 delete `TTL`、复杂 `TTL` 和无 `TTL`。脚本只计划前两张表，后两张表进入 skip report。执行 `ALTER` 后 `system.mutations` 为空，说明 `materialize_ttl_after_modify = 0` 生效。显式执行 `MATERIALIZE TTL` 后，过期 part 移动到 MinIO-backed `bench_s3`，并重压缩为 `ZSTD(12)`；未过期 part 保持在 `default` disk。
