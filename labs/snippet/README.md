# Doris Vector Benchmark

This directory contains a brute-force vector search benchmark for Apache Doris, plus scripts to generate/load the benchmark datasets.

Main files:

- `benchmark.py`: run benchmark scenarios and generate CSV / JSON / PNG results
- `generate_datasets.py`: generate 128D SIFT datasets
- `generate_datasets_768d.py`: generate the base 768D Cohere dataset
- `datasets/sql/load_all.sh`: create tables and load data into Doris
- `BENCHMARK_REPORT.md`: report template / collected results

## Directory Layout

Key paths used by the benchmark:

- `datasets/source/sift_database.tsv`: default 128D source file
- `datasets/source_768d/cohere_1m_train.parquet`: default 768D source file
- 128D generated datasets for 10K/user, 100K/user, 500K/user, and 1M/user
- 768D local base dataset for 10K/user
- SQL DDL files for all 128D / 768D table sizes and PQ variants

Benchmark output goes to `benchmark_results*` directories. `benchmark.py` automatically appends a dimension suffix:

- `--output benchmark_results_warm --dim 128` -> `benchmark_results_warm_128d/`
- `--output benchmark_results_warm --dim 768` -> `benchmark_results_warm_768d/`

## Doris Defaults

`benchmark.py` default connection settings:

- host: `127.0.0.1`
- port: `9030`
- user: `root`
- password: empty
- database: `test_demo`

`load_all.sh` default ports:

- FE HTTP port: `8030`
- FE MySQL/query port: `9030`

If your Doris ports differ, override them with command-line arguments.

## Data Model

Datasets are user-partitioned. Each row is:

```text
user_id<TAB>id<TAB>[embedding]
```

Generated scales:

- `10K/user`: 100 users x 10,000 vectors = 1M rows
- `100K/user`: 100 users x 100,000 vectors = 10M rows
- `500K/user`: 100 users x 500,000 vectors = 50M rows
- `1M/user`: 100 users x 1,000,000 vectors = 100M rows

Defaults in code:

- users: `100`
- shard size: about `1,000,000` rows per shard
- random seed: `42`

## Dataset Generation

### 128D SIFT

Default source path:

```text
datasets/source/sift_database.tsv
```

Run all 128D datasets:

```bash
python3 generate_datasets.py
```

Run a single 128D dataset:

```bash
python3 generate_datasets.py <dataset_name>  # for example, the 100K/user dataset
```

### 768D Cohere

Default source path:

```text
datasets/source_768d/cohere_1m_train.parquet
```

Run base 768D dataset generation:

```bash
python3 generate_datasets_768d.py
```

Behavior:

- If `datasets/source_768d/cohere_1m_train.parquet` is missing, the script tries to download it automatically.
- The script only generates the 10K/user 768D dataset locally.
- Larger 768D tables (`100K/user`, `500K/user`, `1M/user`) are expanded inside Doris by `datasets/sql/load_all.sh` via `INSERT INTO ... SELECT`.

## Load Data Into Doris

Run full load:

```bash
bash datasets/sql/load_all.sh
```

Run with custom Doris address:

```bash
bash datasets/sql/load_all.sh 127.0.0.1 8030 9030 test_demo root
```

Useful environment variables:

- `PARALLEL=4`: shard load concurrency, default `4`
- `SKIP_DDL=1`: skip database/table creation
- `TABLES="10k 100k"`: only load selected scales
- `DIMS="128d"`: load only 128D tables
- `DIMS="768d"`: load only 768D tables
- `DIMS="all"`: load both, default
- `INDEX_MODE="pq_on_disk"`: create/load PQ-on-disk ANN tables instead of brute-force tables
- `LOAD_MODE="etl_only"`: default load mode, supports `etl_only`, `stream_only`

Default load behavior:

- `load_all.sh` now uses **ETL as the default mode** for both 128D and 768D
- In `etl_only` mode, it first stream-loads the 10K/user table as the ETL source table
- Then it expands `10K/user -> 100K/user -> 500K/user -> 1M/user` inside Doris via `INSERT INTO ... SELECT`
- Before stream load or ETL, it checks the target table row count
- If the target table already has the expected row count, that table is skipped automatically

Examples:

```bash
PARALLEL=100 DIMS=768d TABLES="10k" bash datasets/sql/load_all.sh
SKIP_DDL=1 DIMS=128d bash datasets/sql/load_all.sh
INDEX_MODE=pq_on_disk DIMS=768d TABLES="10k" bash datasets/sql/load_all.sh
LOAD_MODE=etl_only DIMS=128d bash datasets/sql/load_all.sh
LOAD_MODE=stream_only DIMS=all bash datasets/sql/load_all.sh
```

## Benchmark Scenarios

`benchmark.py` supports these scenarios:

- `scale`: latency vs table scale
- `topk`: latency vs LIMIT
- `filter`: latency vs filter selectivity
- `distfn`: distance function comparison
- `concurrency`: concurrent throughput on one table
- `largetopk`: larger LIMIT values
- `fullscan`: no `WHERE user_id` filter
- `cache`: repeated same query to observe warming
- `concscale`: concurrent scale test across multiple tables
- `highconc`: higher concurrency levels on one table
- `recall`: in `pq_on_disk` mode, compare approximate search against exact search

If `--scenarios` is omitted, all scenarios run.

## benchmark.py Parameters

### Connection / Basic Output

- `--host`: Doris host, default `127.0.0.1`
- `--port`: Doris query port, default `9030`
- `--user`: Doris user, default `root`
- `--password`: Doris password, default empty
- `--db`: Doris database, default `test_demo`
- `--output`: output directory prefix, default `benchmark_results`

### General Benchmark Control

- `--dim {128,768}`: vector dimension to benchmark
  - `128` uses SIFT tables: `sift_user_*`
  - `768` uses Cohere tables: `cohere_user_*`
- `--search-mode {bruteforce,pq_on_disk}`: select flat scan or pq_on_disk ANN mode
- `--runs`: iterations per test case for latency-style scenarios, default `10`
- `--queries`: number of query vectors sampled from the smallest table, default `5`
- `--scenarios ...`: select scenarios to run; omit to run all
- In `pq_on_disk` mode, `recall` can be run to compare ANN results against exact top-k

### Parallelism Control

- `--parallel N`: apply session-level Doris settings on every connection
  - `parallel_pipeline_task_num = N`
  - `parallel_fragment_exec_instance_num = N`
  - `max_scanners_concurrency = N`
  - default `0`, meaning do not force these settings

### Table Selection

- `--tables SCALE [SCALE ...]`: restrict multi-table scenarios to selected scales
  - affects `scale`, `fullscan`, `concscale`
  - valid values: `10k`, `100k`, `500k`, `1m`
- `--table-key SCALE`: choose the table scale for single-table scenarios
  - affects `topk`, `filter`, `distfn`, `concurrency`, `largetopk`, `cache`, `highconc`
  - default `100k`

### Concurrent Scale (`concscale`) Specific

- `--concurrency-levels N [N ...]`: concurrency array for `concscale`
  - default: `1 4 8 16 32`
- `--duration SECONDS`: duration per `(table scale x concurrency)` case in `concscale`
  - default: `30`
- `--limit N`: `LIMIT` used by `concscale` queries
  - default: `10`

### Report Repair

- `--repair-report DIR`: patch an existing result directory and regenerate charts
  - fixes `dist_fn`
  - adds missing `limit` column for `concscale`
  - re-renders PNG charts

Example:

```bash
python3 benchmark.py --dim 768 --repair-report benchmark_results_warm_768d
```

## Default Scale Mapping

### 128D

- `10k`: 10,000 vectors per user, 1M rows total
- `100k`: 100,000 vectors per user, 10M rows total
- `500k`: 500,000 vectors per user, 50M rows total
- `1m`: 1,000,000 vectors per user, 100M rows total
- brute-force uses exact `l2_distance` with `ASC`
- pq_on_disk uses `l2_distance_approximate` with `ASC`

### 768D

- `10k`: 10,000 vectors per user, 1M rows total
- `100k`: 100,000 vectors per user, 10M rows total
- `500k`: 500,000 vectors per user, 50M rows total
- `1m`: 1,000,000 vectors per user, 100M rows total
- brute-force uses exact `inner_product` with `DESC`
- pq_on_disk uses `inner_product_approximate` with `DESC`

PQ index parameters for pq_on_disk tables:

- 128D: `index_type=pq_on_disk`, `metric_type=l2_distance`, `dim=128`, `pq_m=64`, `pq_nbits=8`
- 768D: `index_type=pq_on_disk`, `metric_type=inner_product`, `dim=768`, `pq_m=384`, `pq_nbits=8`

## Common Commands

Run all 128D benchmarks:

```bash
python3 benchmark.py --dim 128 --output benchmark_results_warm
```

Run all 128D PQ-on-disk benchmarks:

```bash
python3 benchmark.py --dim 128 --search-mode pq_on_disk --output benchmark_results_warm
```

Run all 768D benchmarks with forced single-thread execution:

```bash
python3 benchmark.py --dim 768 --parallel 1 --output benchmark_results_warm
```

Run all 768D PQ-on-disk benchmarks:

```bash
python3 benchmark.py --dim 768 --search-mode pq_on_disk --parallel 1 --output benchmark_results_warm
```

Run only PQ recall evaluation on the 100K/user table:

```bash
python3 benchmark.py --dim 768 --search-mode pq_on_disk --scenarios recall --table-key 100k --output benchmark_results_warm
```

Run only concurrent scale on 768D:

```bash
python3 benchmark.py --dim 768 --parallel 1 --scenarios concscale \
  --concurrency-levels 1 2 4 8 16 32 64 \
  --duration 60 \
  --limit 100 \
  --output benchmark_results_warm
```

Run concurrent scale on 768D PQ-on-disk tables:

```bash
python3 benchmark.py --dim 768 --search-mode pq_on_disk --parallel 1 --scenarios concscale \
  --concurrency-levels 1 2 4 8 16 32 64 \
  --duration 60 \
  --limit 100 \
  --output benchmark_results_warm
```

Run only a subset of tables for multi-table scenarios:

```bash
python3 benchmark.py --dim 768 --scenarios concscale fullscan \
  --tables 10k 100k \
  --output benchmark_results_warm
```

Run single-table scenarios against the 500K/user table:

```bash
python3 benchmark.py --dim 768 --scenarios topk cache highconc \
  --table-key 500k \
  --output benchmark_results_warm
```

## Output Files

Each benchmark output directory contains:

- `*.csv`: per-scenario tabular results
- `summary_<timestamp>.json`: combined JSON summary
- `*.png`: generated charts
- In `pq_on_disk` mode, recall output includes `11_recall_test.png`

For `concscale`, current outputs include:

- `09a_concurrent_scale_qps.png`
- `09b_concurrent_scale_latency.png`
- `09_concurrent_scale_test.png`

## Notes

- Query vectors are sampled from the smallest table of the selected dimension.
- In `pq_on_disk` mode, query vectors are sampled from the `_pq` tables.
- `concscale` uses all tables selected by `--tables`.
- `concurrency` and `highconc` use the single table selected by `--table-key`.
- Result directory names are suffixed automatically with `_128d` / `_768d`, and pq mode adds `_pq_on_disk`.
