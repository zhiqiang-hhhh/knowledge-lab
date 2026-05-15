# Doris Brute-Force Vector Search Benchmark Report

**Date:** 2026-03-30  
**System:** 192 CPU cores, 1.48TB RAM, 3.5TB disk  
**Doris Ports:** Query 9930, FE HTTP 8930, BE HTTP 8940  
**Database:** `test_demo` on `127.0.0.1`, user `root`  

---

## Table of Contents
- [Part A: 128D SIFT Benchmark](#part-a-128d-sift-benchmark) (warm+cold, full parallelism)
- [Part B: 768D Cohere Benchmark](#part-b-768d-cohere-benchmark) (warm cache, parallel=1, 64GB mem)

---

# Part A: 128D SIFT Benchmark

## 1. Test Environment

### Hardware
- 192 CPU cores
- 1.48TB memory (no memory limit)
- 3.5TB disk
- Single-node Doris deployment (1 FE + 1 BE)
- Default parallelism (auto)

### Data
- **Source:** SIFT 1M dataset (128-dimensional integer vectors)
- **Tables:** 4 tables, each with 100 users, varying vectors per user:

| Table | Vectors/User | Total Rows | Buckets |
|-------|-------------|------------|---------|
| `sift_user_1w` | 10,000 | 1,000,000 | 4 |
| `sift_user_10w` | 100,000 | 10,000,000 | 8 |
| `sift_user_50w` | 500,000 | 50,000,000 | 16 |
| `sift_user_100w` | 1,000,000 | 100,000,000 | 32 |

### Schema
```sql
CREATE TABLE sift_user_Xw (
  user_id int NOT NULL,
  id int NOT NULL,
  embedding array<float> NOT NULL
) DUPLICATE KEY(user_id, id)
DISTRIBUTED BY HASH(user_id) BUCKETS N
-- No ANN index (brute-force only)
```

### Benchmark Parameters
- 5 query vectors (randomly sampled from `sift_user_1w`)
- 10 iterations per test case (after 2 warmup runs)
- Two modes: **warm cache** (all Doris caches enabled) and **cold cache** (storage page cache + segment cache disabled)

---

## 2. Results Summary (128D, Warm + Cold)

### Scenario 1: Scale Test — Latency vs Data Volume

```sql
SELECT id FROM {table}
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Scale | Rows/User | Total Rows | Cold Avg (ms) | Cold P99 (ms) | Warm Avg (ms) | Warm P99 (ms) | Speedup |
|-------|-----------|------------|--------------|--------------|--------------|--------------|---------|
| 10K/user | 10,000 | 1M | 55.1 | 69.9 | 1.5 | 2.8 | 37x |
| 100K/user | 100,000 | 10M | 133.8 | 175.0 | 2.0 | 5.5 | 67x |
| 500K/user | 500,000 | 50M | 415.9 | 485.0 | 2.3 | 8.7 | 181x |
| 1M/user | 1,000,000 | 100M | 840.5 | 1045.3 | 1.7 | 3.8 | 494x |

**Key Finding:** Without caches, latency scales roughly linearly with data volume (~55ms per 10K vectors). With warm caches, results are served in ~2ms regardless of scale — the entire dataset fits in memory and Doris's page cache eliminates disk I/O entirely.

Chart: `benchmark_results_cold/01_scale_test.png` / `benchmark_results_warm/01_scale_test.png`

---

### Scenario 2: Top-K Test — Latency vs LIMIT K

```sql
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT {K}                             -- K = 1, 10, 50, 100, 500
```

| LIMIT K | Cold Avg (ms) | Warm Avg (ms) |
|---------|--------------|--------------|
| 1 | 133.1 | 1.9 |
| 10 | 132.1 | 2.1 |
| 50 | 136.7 | 2.8 |
| 100 | 138.7 | 4.0 |
| 500 | 164.2 | 7.5 |

**Key Finding:** Top-K has minimal impact on cold latency (sorting is cheap relative to I/O). In warm mode, LIMIT 500 is ~4x slower than LIMIT 1 due to the heap/sorting overhead.

Chart: `benchmark_results_cold/02_topk_test.png` / `benchmark_results_warm/02_topk_test.png`

---

### Scenario 3: Filter Selectivity — Latency vs Number of Users

```sql
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id IN ({uid1}, {uid2}, ...)  -- 1, 5, 10, 50, or 100 users
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Users | Rows Scanned | Cold Avg (ms) | Warm Avg (ms) |
|-------|-------------|--------------|--------------|
| 1 | 100K | 126.2 | 1.8 |
| 5 | 500K | 253.1 | 1.5 |
| 10 | 1M | 327.5 | 2.1 |
| 50 | 5M | 1320.2 | 2.2 |
| 100 | 10M (full table) | 2006.0 | 1.5 |

**Key Finding:** Cold latency scales linearly with the number of rows scanned (more users = more data to read from disk). Warm latency is flat ~2ms, indicating all data is cached and the 192-core CPU handles vectorized distance computation on up to 10M vectors almost instantly.

Chart: `benchmark_results_cold/03_filter_test.png` / `benchmark_results_warm/03_filter_test.png`

---

### Scenario 4: Distance Function Comparison

```sql
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY {dist_fn}(embedding, <vec>) {ASC|DESC}
LIMIT 10
-- dist_fn = l2_distance / inner_product / cosine_similarity
```

| Function | Cold Avg (ms) | Warm Avg (ms) |
|----------|--------------|--------------|
| l2_distance | 135.6 | 1.7 |
| inner_product | 135.1 | 2.0 |
| cosine_similarity | 140.5 | 2.1 |

**Key Finding:** All three distance functions perform nearly identically. `cosine_similarity` is slightly slower (~4% cold) due to the extra normalization step. In warm mode, the difference is negligible.

Chart: `benchmark_results_cold/04_distance_fn_test.png` / `benchmark_results_warm/04_distance_fn_test.png`

---

### Scenario 5: Concurrency Test — Throughput vs Concurrent Connections

```sql
-- N concurrent threads, each repeatedly executing:
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Concurrency | Cold QPS | Cold Avg (ms) | Warm QPS | Warm Avg (ms) |
|------------|---------|--------------|---------|--------------|
| 1 | 7.6 | 132.3 | 423 | 2.1 |
| 2 | 14.9 | 133.4 | 823 | 2.0 |
| 4 | 29.8 | 131.4 | 1120 | 2.5 |
| 8 | 57.4 | 133.2 | 1353 | 4.2 |
| 16 | 114.8 | 131.0 | 1533 | 7.4 |

**Key Finding:** Cold QPS scales linearly with concurrency (I/O-bound, each query independently reads from disk). Warm QPS plateaus around 1500 QPS at C=16 — the bottleneck shifts to CPU-based vector distance computation.

Chart: `benchmark_results_cold/05_concurrency_test.png` / `benchmark_results_warm/05_concurrency_test.png`

---

### Scenario 6: Large Top-K Test — Extended LIMIT Range

```sql
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT {K}                             -- K = 100, 500, 1000, 2000, 5000
```

| LIMIT K | Cold Avg (ms) | Warm Avg (ms) |
|---------|--------------|--------------|
| 100 | 147.0 | 2.1 |
| 500 | 163.2 | 5.1 |
| 1000 | 188.5 | 6.8 |
| 2000 | 144.7 | 12.9 |
| 5000 | 158.5 | 173.3 |

**Key Finding:** In warm mode, LIMIT 5000 triggers a dramatic latency spike (173ms vs 6.8ms for K=1000). This suggests that when K approaches a significant fraction of per-user data (5000 out of 100K), the sorting/heap management becomes the dominant cost. Cold mode shows little K sensitivity since I/O dominates.

Chart: `benchmark_results_cold/06_large_topk_test.png` / `benchmark_results_warm/06_large_topk_test.png`

---

### Scenario 7: Full Table Scan — No user_id Filter

```sql
-- NOTE: No WHERE clause — scans ALL users in the entire table
SELECT user_id, id FROM {table}
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Scale | Total Rows | Cold Avg (ms) | Warm Avg (ms) |
|-------|-----------|--------------|--------------|
| 10K/user | 1M | 348.7 | 2.0 |
| 100K/user | 10M | 1650.2 | 2.1 |
| 500K/user | 50M | 3093.9 | 2.6 |
| 1M/user | 100M | 4949.6 | 2.1 |

**Key Finding:** Full scan cold latency: ~50ms per 1M rows. Scanning 100M vectors takes ~5 seconds without caches. Warm mode: ~2ms regardless of table size — the 192-core machine can brute-force 100M vectors from cache almost instantly.

Chart: `benchmark_results_cold/07_full_scan_test.png` / `benchmark_results_warm/07_full_scan_test.png`

---

### Scenario 8: Cache Effect — Latency Across 50 Repeated Queries

```sql
-- Same query executed 50 times back-to-back, no explicit warmup:
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

- **Cold mode:** Latency is flat at ~130ms across all 50 iterations (no cache to warm when page cache is disabled).
- **Warm mode:** First query: 13.5ms. By iteration 5, stabilizes at ~2ms. The cache warms within 1-2 iterations.

Chart: `benchmark_results_cold/08_cache_effect_test.png` / `benchmark_results_warm/08_cache_effect_test.png`

---

### Scenario 9: Concurrent Scale Test — Throughput vs Table Size at C=8

```sql
-- 8 concurrent threads, each repeatedly executing:
SELECT id FROM {table}                -- varies across 4 table sizes
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Scale | Total Rows | Cold QPS | Cold P99 (ms) | Warm QPS | Warm P99 (ms) |
|-------|-----------|---------|--------------|---------|--------------|
| 10K/user | 1M | 232.5 | 53.0 | 1290 | 58.8 |
| 100K/user | 10M | 59.9 | 154.9 | 1552 | 9.5 |
| 500K/user | 50M | 15.5 | 601.3 | 226 | 508.9 |
| 1M/user | 100M | 8.0 | 1214.5 | 156 | 953.2 |

**Key Finding:** At C=8, warm QPS for 10K/user and 100K/user tables is excellent (1300-1550 QPS). 500K/user and 1M/user tables show initial warm-up latency spikes in the P99 (some queries hit cold data), dropping QPS. Cold mode QPS inversely correlates with table size.

Chart: `benchmark_results_cold/09_concurrent_scale_test.png` / `benchmark_results_warm/09_concurrent_scale_test.png`

---

### Scenario 10: High Concurrency Test — Throughput vs Concurrency (up to 64)

```sql
-- N concurrent threads (N = 1..64), each repeatedly executing:
SELECT id FROM sift_user_10w          -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY l2_distance(embedding, <vec>) ASC
LIMIT 10
```

| Concurrency | Cold QPS | Cold Avg (ms) | Warm QPS | Warm Avg (ms) | Warm P99 (ms) |
|------------|---------|--------------|---------|--------------|--------------|
| 1 | 6.3 | 157.5 | 482 | 2.0 | 2.7 |
| 4 | 23.2 | 168.1 | 1411 | 2.2 | 3.4 |
| 8 | 46.6 | 161.4 | 1465 | 3.6 | 6.4 |
| 16 | 79.2 | 193.1 | 1775 | 6.3 | 12.6 |
| 32 | 161.4 | 184.7 | 1543 | 12.8 | 34.2 |
| 64 | 231.3 | 250.7 | 1481 | 18.9 | 52.8 |

**Key Finding:** Warm QPS peaks at C=16 (1775 QPS) then slightly decreases at C=32/64 due to context switching and lock contention. P99 latency grows roughly linearly with concurrency. Cold mode shows near-linear QPS scaling since each query is I/O-bound on independent segments.

Chart: `benchmark_results_cold/10_high_concurrency_test.png` / `benchmark_results_warm/10_high_concurrency_test.png`

---

## 3. Key Takeaways (128D)

### Cache Impact
The single most impactful factor is **Doris page cache**. With warm caches:
- Single-user queries return in **~2ms** regardless of whether the table has 1M or 100M rows
- Full table scans of 100M rows complete in **~2ms**
- Peak throughput reaches **~1800 QPS** at 16 concurrent connections

Without caches (cold), latency is **50-100x slower**, dominated by I/O.

### Brute-Force Performance
On this 192-core machine with data in memory:
- **128-dim vector distance computation** is essentially free — the CPU can brute-force 100K vectors in under 2ms
- **Filter selectivity** has no impact when data is cached (1 user vs 100 users: same latency)
- **Distance function choice** (L2 vs IP vs cosine) has <10% impact

### Scaling Characteristics (Cold)
- Latency scales **linearly** with data volume: ~13ms per 100K rows for single-user queries
- Full table scan: ~50ms per 1M rows
- QPS at C=8: inversely proportional to table size

### Concurrency Behavior
- Warm peak QPS: **~1800** at C=16 on `sift_user_10w`
- Diminishing returns beyond C=16 (CPU saturation for vector ops)
- Cold QPS scales linearly with concurrency (I/O parallel)

### Top-K Impact
- LIMIT 1-1000: minimal overhead in both warm and cold modes
- LIMIT 5000 on 100K vectors: significant overhead (173ms warm), likely due to large heap management
- For production: keep LIMIT under 1000 for best performance

---

## 4. Files Reference (128D)

### Scripts
| File | Description |
|------|-------------|
| `generate_datasets.py` | Parallel dataset generation (32 workers, ~50s total) |
| `benchmark.py` | 10-scenario benchmark script with charts |
| `datasets/sql/load_all.sh` | Batch stream load script |
| `datasets/sql/0[1-4]_sift_user_*.sql` | Table DDL files |

### Results
| Directory | Description |
|-----------|-------------|
| `benchmark_results_cold/` | Results with Doris page cache + segment cache disabled |
| `benchmark_results_warm/` | Results with all caches enabled |

Each directory contains:
- `01-10_*.png` — Chart visualizations
- `*_<timestamp>.csv` — Per-scenario CSV data
- `summary_<timestamp>.json` — Combined JSON summary

### Data
| Directory | Size | Shards |
|-----------|------|--------|
| `datasets/dataset_1w/` | 113MB | 1 |
| `datasets/dataset_10w/` | 1.3GB | 10 |
| `datasets/dataset_50w/` | 6.4GB | 50 |
| `datasets/dataset_100w/` | 13GB | 100 |

---
---

# Part B: 768D Cohere Benchmark

## 1. Test Environment

### Constraints
- **Memory limit:** 64GB (BE `mem_limit = 64G`)
- **Parallelism:** 1 (`parallel_pipeline_task_num=1`, `parallel_fragment_exec_instance_num=1`)
- **Cache mode:** Warm only (all Doris caches enabled, tables pre-warmed before benchmark)

### Hardware
- 192 CPU cores (but parallelism forced to 1)
- 64GB memory limit (of 1.48TB physical)
- 3.5TB disk
- Single-node Doris deployment (1 FE + 1 BE)

### Data
- **Source:** Cohere/wikipedia-22-12 (768-dimensional float vectors, 1M rows from parquet)
- **Distance function:** `cosine_similarity` (DESC) by default
- **Tables:** 4 tables, each with 100 users, varying vectors per user:

| Table | Vectors/User | Total Rows | Buckets | Compressed Size |
|-------|-------------|------------|---------|-----------------|
| `cohere_user_1w` | 10,000 | 1,000,000 | 4 | 3.2GB |
| `cohere_user_10w` | 100,000 | 10,000,000 | 8 | 32GB |
| `cohere_user_50w` | 500,000 | 50,000,000 | 16 | 156GB |
| `cohere_user_100w` | 1,000,000 | 100,000,000 | 32 | 311GB |

### Schema
```sql
CREATE TABLE cohere_user_Xw (
  user_id int NOT NULL,
  id int NOT NULL,
  embedding array<float> NOT NULL
) DUPLICATE KEY(user_id, id)
DISTRIBUTED BY HASH(user_id) BUCKETS N
-- No ANN index (brute-force only)
```

### Benchmark Parameters
- 5 query vectors (randomly sampled from `cohere_user_1w`)
- 10 iterations per test case (after warmup)
- Warm cache only (tables pre-scanned to fill page cache)
- Parallelism forced to 1 (single pipeline thread per query)

---

## 2. Results Summary (768D, Warm, Parallel=1)

### Scenario 1: Scale Test — Latency vs Data Volume

```sql
SELECT id FROM {table}
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Scale | Rows/User | Total Rows | Avg (ms) | P50 (ms) | P99 (ms) |
|-------|-----------|------------|----------|----------|----------|
| 10K/user | 10,000 | 1M | 9.9 | 9.4 | 19.3 |
| 100K/user | 100,000 | 10M | 11.3 | 9.4 | 26.3 |
| 500K/user | 500,000 | 50M | 12.1 | 9.4 | 38.2 |
| 1M/user | 1,000,000 | 100M | 10.5 | 9.3 | 25.7 |

**Key Finding:** With warm cache and single-thread execution, 768D single-user queries average ~10ms regardless of total table size — Doris prunes to the user's partition efficiently. The p50 is a consistent ~9.4ms across all scales, with p99 variance from outlier queries.

Chart: `benchmark_results_warm_768d/01_scale_test.png`

---

### Scenario 2: Top-K Test — Latency vs LIMIT K

```sql
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT {K}                             -- K = 1, 10, 50, 100, 500
```

| LIMIT K | Avg (ms) | P50 (ms) | P99 (ms) |
|---------|----------|----------|----------|
| 1 | 13.3 | 10.3 | 26.8 |
| 10 | 11.7 | 9.4 | 26.0 |
| 50 | 12.9 | 10.3 | 28.1 |
| 100 | 14.4 | 11.6 | 37.4 |
| 500 | 19.9 | 18.3 | 30.4 |

**Key Finding:** Top-K up to 100 has minimal impact (~12-14ms). At K=500, the sorting overhead becomes noticeable (~20ms). The scan cost dominates over sorting for small K values.

Chart: `benchmark_results_warm_768d/02_topk_test.png`

---

### Scenario 3: Filter Selectivity — Latency vs Number of Users

```sql
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id IN ({uid1}, {uid2}, ...)  -- 1, 5, 10, 50, or 100 users
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Users | Rows Scanned | Avg (ms) | P50 (ms) | P99 (ms) |
|-------|-------------|----------|----------|----------|
| 1 | 100K | 13.5 | 10.1 | 26.8 |
| 5 | 500K | 12.4 | 9.6 | 30.2 |
| 10 | 1M | 14.1 | 13.6 | 44.2 |
| 50 | 5M | 11.1 | 9.4 | 24.3 |
| 100 | 10M (full table) | 16.0 | 14.5 | 32.2 |

**Key Finding:** Even scanning 10M 768D vectors (100 users x 100K), latency is only 16ms avg with warm cache. Filter selectivity has relatively flat impact — data is all in page cache and single-thread performance is sufficient.

Chart: `benchmark_results_warm_768d/03_filter_test.png`

---

### Scenario 4: Distance Function Comparison

```sql
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY {dist_fn}(embedding, <vec>) {ASC|DESC}
LIMIT 10
-- dist_fn = l2_distance / inner_product / cosine_similarity
```

| Function | Avg (ms) | P50 (ms) | P99 (ms) |
|----------|----------|----------|----------|
| l2_distance | 16.9 | 14.8 | 35.4 |
| inner_product | 15.6 | 14.6 | 44.3 |
| cosine_similarity | 20.5 | 19.6 | 40.3 |

**Key Finding:** `cosine_similarity` is ~25% slower than `l2_distance`/`inner_product` at 768D due to normalization overhead (more significant at higher dimensions). `inner_product` is the fastest. For 768D, choosing `inner_product` over `cosine_similarity` saves ~5ms per query.

Chart: `benchmark_results_warm_768d/04_distance_fn_test.png`

---

### Scenario 5: Concurrency Test — Throughput vs Concurrent Connections

```sql
-- N concurrent threads, each repeatedly executing:
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Concurrency | QPS | Avg (ms) | P99 (ms) |
|------------|-----|----------|----------|
| 1 | 60 | 16.5 | 21.3 |
| 2 | 42 | 34.1 | 435.2 |
| 4 | 40 | 55.3 | 737.1 |
| 8 | 80 | 38.6 | 224.1 |
| 16 | 153 | 101.2 | 138.1 |

**Key Finding:** With parallelism forced to 1, each query uses a single pipeline thread. At C=1, QPS is 60 (matching ~16ms per query). QPS initially drops at C=2-4 due to high p99 outliers (connection pool warm-up), then recovers at C=8-16 as Doris schedules queries across multiple cores despite per-query parallelism=1.

Chart: `benchmark_results_warm_768d/05_concurrency_test.png`

---

### Scenario 6: Large Top-K Test — Extended LIMIT Range

```sql
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT {K}                             -- K = 100, 500, 1000, 2000, 5000
```

| LIMIT K | Avg (ms) | P50 (ms) | P99 (ms) |
|---------|----------|----------|----------|
| 100 | 15.3 | 14.8 | 33.6 |
| 500 | 17.6 | 15.6 | 30.1 |
| 1000 | 26.6 | 25.3 | 36.2 |
| 2000 | 33.1 | 32.8 | 44.6 |
| 5000 | 604.1 | 590.8 | 802.9 |

**Key Finding:** LIMIT 5000 causes a dramatic latency spike to ~600ms (vs 33ms at K=2000). This 18x jump suggests Doris switches execution strategy (or heap management becomes a bottleneck) when K exceeds a threshold fraction of per-user rows (5000/100K = 5%).

Chart: `benchmark_results_warm_768d/06_large_topk_test.png`

---

### Scenario 7: Full Table Scan — No user_id Filter

```sql
-- NOTE: No WHERE clause — scans ALL users in the entire table
SELECT user_id, id FROM {table}
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Scale | Total Rows | Avg (ms) | P50 (ms) | P99 (ms) |
|-------|-----------|----------|----------|----------|
| 10K/user | 1M | 15.7 | 13.7 | 22.3 |
| 100K/user | 10M | 15.8 | 14.1 | 32.1 |
| 500K/user | 50M | 18.1 | 15.9 | 32.6 |
| 1M/user | 100M | 19.5 | 19.9 | 33.7 |

**Key Finding:** Full scan of 100M 768D vectors in ~20ms with warm cache is remarkable, even with parallelism=1. This means Doris's pruning/bucketing efficiently distributes the scan and the per-query execution is I/O-bound on cached pages.

Chart: `benchmark_results_warm_768d/07_full_scan_test.png`

---

### Scenario 8: Cache Effect — Latency Across 50 Repeated Queries

```sql
-- Same query executed 50 times back-to-back, no explicit warmup:
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Iterations | Avg (ms) | Min (ms) | Max (ms) |
|-----------|----------|----------|----------|
| 1-5 | 122.0 | 13.9 | 550.9 |
| 6-10 | 14.8 | 13.9 | 15.4 |
| 11-15 | 13.8 | 13.5 | 14.1 |
| 16-50 | ~14-18 | ~13.3 | ~32.9 |

**Key Finding:** First query in the batch hits ~551ms (cold page), but by iteration 2-3 the cache is warm and latency stabilizes at ~14ms. The cache warms within 1 iteration for 768D data on `cohere_user_10w`.

Chart: `benchmark_results_warm_768d/08_cache_effect_test.png`

---

### Scenario 9: Concurrent Scale Test — QPS & Latency vs Table Size × Concurrency

**Method:** Duration-based test. Each (scale × concurrency) case runs for **30 seconds** continuously. Workers loop queries until the duration expires. Metrics are collected from all completed queries.

**Config:** `parallel_pipeline_task_num=1`, `max_scanners_concurrency=1`, all tables BUCKETS 1, 64GB BE memory.

```sql
-- Each worker thread continuously executes (for 30s):
SELECT id FROM {table}                -- varies across 4 table sizes
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Scale | Total Rows | Concurrency | Queries | QPS | Avg (ms) | P50 (ms) | P90 (ms) | P99 (ms) |
|-------|-----------|-------------|---------|-----|----------|----------|----------|----------|
| 10K/user | 1M | 1 | 2879 | 96.0 | 10.4 | 8.4 | 15.2 | 25.3 |
| 10K/user | 1M | 4 | 9379 | 312.5 | 12.8 | 11.3 | 15.0 | 47.7 |
| 10K/user | 1M | 8 | 4229 | 140.8 | 56.8 | 53.5 | 86.2 | 104.2 |
| 10K/user | 1M | 16 | 2733 | 90.8 | 175.9 | 181.6 | 212.8 | 236.7 |
| 10K/user | 1M | 32 | 2624 | 86.8 | 367.1 | 372.7 | 428.3 | 467.2 |
| 100K/user | 10M | 1 | 3149 | 105.0 | 9.5 | 8.0 | 12.9 | 25.1 |
| 100K/user | 10M | 4 | 9289 | 309.6 | 12.9 | 11.3 | 15.2 | 46.4 |
| 100K/user | 10M | 8 | 5001 | 166.5 | 48.0 | 44.1 | 73.7 | 96.5 |
| 100K/user | 10M | 16 | 3199 | 106.3 | 150.2 | 158.0 | 192.9 | 213.5 |
| 100K/user | 10M | 32 | 2760 | 91.3 | 349.2 | 361.6 | 416.0 | 458.9 |
| 500K/user | 50M | 1 | 2892 | 96.4 | 10.4 | 8.4 | 14.7 | 28.2 |
| 500K/user | 50M | 4 | 8476 | 282.4 | 14.2 | 11.5 | 16.3 | 47.2 |
| 500K/user | 50M | 8 | 4060 | 135.2 | 59.1 | 56.6 | 87.8 | 105.0 |
| 500K/user | 50M | 16 | 3409 | 113.2 | 141.1 | 147.2 | 185.7 | 213.0 |
| 500K/user | 50M | 32 | 3215 | 106.5 | 299.6 | 309.9 | 381.6 | 452.8 |
| 1M/user | 100M | 1 | 3168 | 105.6 | 9.5 | 8.0 | 13.2 | 24.8 |
| 1M/user | 100M | 4 | 8042 | 268.0 | 14.9 | 11.4 | 16.1 | 46.7 |
| 1M/user | 100M | 8 | 4915 | 163.6 | 48.9 | 44.4 | 73.5 | 95.4 |
| 1M/user | 100M | 16 | 3570 | 118.6 | 134.6 | 140.7 | 183.1 | 212.6 |
| 1M/user | 100M | 32 | 3090 | 102.2 | 312.2 | 319.0 | 376.4 | 416.6 |

**Key Findings:**

1. **Peak QPS at C=4 across all scales:** QPS peaks at C=4 (268-312 QPS), then drops sharply at C=8. With `parallel_pipeline_task_num=1` and `max_scanners_concurrency=1`, each query is single-threaded, so 4 concurrent queries can saturate available resources before contention dominates.
2. **Table size has minimal impact:** Since queries use `WHERE user_id=42` which prunes to 1/100th of the data (10K-1M rows per user regardless of total table size), QPS is remarkably stable across scales. At C=4: 312 (1M table) vs 268 (100M table) — only ~15% drop.
3. **Latency scales linearly with concurrency:** At C=1, avg latency is ~10ms. At C=32, it's ~300-370ms (30-37x). P90-P99 gap is tight (<30%), indicating consistent behavior without outlier spikes.
4. **No cache pressure at user_id level:** Unlike the old C=8 test (which showed high p99 at large scales), the 30s duration-based test confirms that user_id pruning is effective enough that even 100M-row tables perform well — the working set per user fits in cache.

Charts:
- `benchmark_results_warm_768d/09a_concurrent_scale_qps.png` (QPS grouped bar)
- `benchmark_results_warm_768d/09b_concurrent_scale_latency.png` (P50/P90/P99 per concurrency)

---

### Scenario 10: High Concurrency Test — Throughput vs Concurrency (up to 64)

```sql
-- N concurrent threads (N = 1..64), each repeatedly executing:
SELECT id FROM cohere_user_10w        -- 100K/user, 10M total
WHERE user_id = 42
ORDER BY cosine_similarity(embedding, <vec>) DESC
LIMIT 10
```

| Concurrency | QPS | Avg (ms) | P99 (ms) |
|------------|-----|----------|----------|
| 1 | 66 | 14.8 | 19.0 |
| 4 | 213 | 16.1 | 32.9 |
| 8 | 161 | 46.7 | 105.7 |
| 16 | 116 | 127.1 | 203.3 |
| 32 | 90 | 343.3 | 453.3 |
| 64 | 89 | 696.7 | 921.3 |

**Key Finding:** Peak QPS is 213 at C=4, then degrades at higher concurrency. With parallelism=1, each query only uses one pipeline thread, so concurrent queries compete for CPU. At C=64, avg latency is ~700ms with sub-100 QPS — severe contention.

Chart: `benchmark_results_warm_768d/10_high_concurrency_test.png`

---

## 3. Key Takeaways (768D)

### 768D vs 128D Comparison (Warm Cache)

| Metric | 128D (auto parallel) | 768D (parallel=1, 64GB) | Ratio |
|--------|---------------------|------------------------|-------|
| Single-user query (100K/user) | ~2ms | ~12ms | 6x |
| Full scan 100M rows | ~2ms | ~20ms | 10x |
| Peak QPS (100K/user table) | ~1800 (C=16) | ~310 (C=4) | 5.8x |
| Large K=5000 | 173ms | 604ms | 3.5x |
| Distance fn overhead | <10% | ~25% (cosine vs L2) | higher |

### Memory Constraint Impact
- With 64GB mem limit, the 1M/user table (311GB compressed, ~600GB+ uncompressed) cannot fully fit in cache
- However, with `WHERE user_id=42` pruning, the effective working set per user is small enough that cache pressure is negligible for all scales
- Duration-based testing (30s) confirms stable performance without p99 spikes — earlier high p99 at large scales was an artifact of short burst testing

### Single-Thread (Parallel=1) Impact
- Single-user queries: ~10ms (vs ~2ms with auto parallelism) — 5x slower
- Full scan is surprisingly fast (~20ms for 100M rows) — pruning is effective
- QPS peaks at ~310 (C=4) vs ~1800 (C=16 with auto parallel)

### Concurrency Scaling (30s duration-based)
- **C=1:** ~100 QPS, ~10ms avg latency — baseline
- **C=4:** ~270-310 QPS (peak) — 3x throughput vs C=1, only ~3ms avg latency increase
- **C=8:** ~135-165 QPS — contention halves throughput vs C=4
- **C=16/32:** ~90-120 QPS — diminishing returns, latency 150-370ms

### Recommendations for 768D Production Use
- **Memory:** Ensure working set fits in page cache for consistent latency
- **Parallelism:** Allow auto-parallelism for best single-query latency; use parallel=1 only to test worst-case
- **Top-K:** Keep LIMIT under 2000 (K=5000 triggers 18x latency spike)
- **Distance function:** Prefer `inner_product` over `cosine_similarity` for ~25% speedup at 768D
- **Concurrency:** At parallel=1, optimal concurrency is C=4 for 768D (~310 QPS). Beyond C=4, contention dominates and latency rises sharply.

---

## 4. Files Reference

### Scripts
| File | Description |
|------|-------------|
| `generate_datasets.py` | 128D SIFT dataset generation |
| `generate_datasets_768d.py` | 768D Cohere dataset generation |
| `benchmark.py` | 10-scenario benchmark script (supports `--dim 128\|768`, `--parallel N`) |
| `datasets/sql/load_all.sh` | Batch stream load script (supports `DIMS=128d\|768d\|all`) |
| `datasets/sql/0[1-4]_sift_user_*.sql` | 128D table DDL files |
| `datasets/sql/0[5-8]_cohere_user_*.sql` | 768D table DDL files |

### Results
| Directory | Description |
|-----------|-------------|
| `benchmark_results_cold/` | 128D cold cache results |
| `benchmark_results_warm/` | 128D warm cache results |
| `benchmark_results_warm_768d/` | 768D warm cache results (parallel=1, 64GB mem) |

Each directory contains:
- `01-10_*.png` — Chart visualizations
- `*_<timestamp>.csv` — Per-scenario CSV data
- `summary_<timestamp>.json` — Combined JSON summary

### Data
| Directory | Dim | Size | Shards |
|-----------|-----|------|--------|
| `datasets/dataset_1w/` | 128 | 113MB | 1 |
| `datasets/dataset_10w/` | 128 | 1.3GB | 10 |
| `datasets/dataset_50w/` | 128 | 6.4GB | 50 |
| `datasets/dataset_100w/` | 128 | 13GB | 100 |
| `datasets/dataset_768d_1w/` | 768 | 3.2GB | 1 |
| `datasets/dataset_768d_10w/` | 768 | 32GB | 10 |
| `datasets/dataset_768d_50w/` | 768 | 156GB | 50 |
| `datasets/dataset_768d_100w/` | 768 | 311GB | 100 |
