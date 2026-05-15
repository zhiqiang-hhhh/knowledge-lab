---
name: benchmark-report
description: Generate a Doris vector search performance report from benchmark result CSV/JSON data, following the standardized report format used in this project.
---

## When to use me

Use this skill when the user asks to generate a performance report or benchmark report from benchmark result files (CSV, JSON) produced by `benchmark.py`.

## Input

The user will provide:
1. **Result directory** — path like `benchmark_results_warm_768d/` containing CSV and/or JSON output from `benchmark.py`
2. **Hardware spec** — e.g. "FE 8C16GB, BE 16C64GB"
3. **Test command** — the exact `python3 benchmark.py ...` command used
4. **Additional context** — bucket count, special notes, etc.

## Workflow

### Step 1: Read the data

1. List the result directory to find all CSV and JSON files.
2. Read every CSV and the `summary_*.json` file to understand which scenarios were tested.
3. Read `benchmark.py` argument parser (around line 1020-1070) to understand the flags used in the test command — especially `--parallel`, `--dim`, `--scenarios`, `--concurrency-levels`, `--duration`, `--output`.

### Step 2: Extract environment info from the test command

From the test command, determine:
- `--dim` → vector dimension (128 or 768)
- `--parallel` → parallelism setting (0=auto, 1=serial, N=fixed)
- `--scenarios` → which scenarios were run
- `--concurrency-levels` → concurrency levels tested
- `--duration` → duration per test case in seconds
- `--output` → output directory base name

Combined with user-provided hardware spec, derive:
- FE/BE CPU and memory
- Bucket count
- Cache mode (warm/cold)

### Step 3: Determine table naming convention

Use English units for scale labels, NOT Chinese "w" (万):
- 1w (10,000) → 10K
- 10w (100,000) → 100K
- 50w (500,000) → 500K
- 100w (1,000,000) → 1M

Table names follow the same convention:
- `cohere_user_1w` → `cohere_user_10k`
- `cohere_user_10w` → `cohere_user_100k`
- `cohere_user_50w` → `cohere_user_500k`
- `cohere_user_100w` → `cohere_user_1m`

Similarly for 128D SIFT tables:
- `sift_user_1w` → `sift_user_10k`, etc.

### Step 4: Generate the report

Create a file named `PERFORMANCE_REPORT_<DIM>D.md` (e.g. `PERFORMANCE_REPORT_768D.md`) with the following structure:

```markdown
# Doris <DIM>D Brute-Force Vector Search Performance Report

**Date:** <YYYY-MM-DD>
**System:** <hardware summary, e.g. "FE 8C16GB + BE 16C64GB">
**Doris Ports:** Query 9930, FE HTTP 8930, BE HTTP 8940
**Database:** `test_demo` on `127.0.0.1`, user `root`

---

## 1. Test Environment

### Hardware
- **FE:** <cores> CPU cores, <mem> memory
- **BE:** <cores> CPU cores, <mem> memory
- Single-node Doris deployment (1 FE + 1 BE)

### Configuration
- **Parallelism:** <value and session variable details>
- **Cache mode:** <Warm/Cold>
- **Duration:** <N> seconds per test case

### Test Command
\```bash
<exact command>
\```

### Data
- **Source:** <dataset source description>
- **Distance function:** <function> (<ASC|DESC>)
- **Tables:** <N> tables, each with <N> users, varying vectors per user:

| Table | Vectors/User | Total Rows | Buckets | Compressed Size |
|-------|-------------|------------|---------|-----------------|
| ... | ... | ... | ... | ... |

### Schema
\```sql
<CREATE TABLE DDL>
\```

### Benchmark Parameters
- <list all key parameters>

---

## 2. Results Summary (<DIM>D, <Cache>, Parallel=<N>)

### <Scenario Name> — <Description>

**Method:** <test method description>

\```sql
<example query>
\```

<UNIFIED TABLE with Scale column — merge all table sizes into one table>

| Scale | Concurrency | Queries | QPS | Avg (ms) | P50 (ms) | P90 (ms) | P99 (ms) |
|-------|------------|---------|-----|----------|----------|----------|----------|
| 10K/user | 1 | ... | ... | ... | ... | ... | ... |
| 10K/user | 2 | ... | ... | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... | ... | ... |
| 100K/user | 1 | ... | ... | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Key Findings:**
- **10K/user:** <analysis>
- **100K/user:** <analysis>
- **500K/user:** <analysis>
- **1M/user:** <analysis>

---

### Cross-Scale QPS Summary (Peak Concurrency)

| Scale | Vectors/User | Total Rows | Peak QPS | Best Concurrency | Avg Latency @ Peak |
|-------|-------------|------------|----------|-------------------|--------------------|
| ... | ... | ... | ... | ... | ... |

---

### Cross-Scale Single-Thread Latency (C=1)

| Scale | Vectors/User | Avg (ms) | P50 (ms) | P90 (ms) | P99 (ms) |
|-------|-------------|----------|----------|----------|----------|
| ... | ... | ... | ... | ... | ... |

---

## 3. Key Findings

### Latency Scaling with Data Volume
<analysis of how latency scales with vector count>

### Concurrency Behavior
<analysis of QPS scaling, optimal concurrency, diminishing returns>

### Tail Latency (P99) Behavior
<analysis of P99/P50 ratio at different concurrency levels>

### Comparison: This Test vs Previous Tests
<if prior results exist in BENCHMARK_REPORT.md, compare hardware, config, and key metrics>

### Practical Throughput Limits
| Use Case | Vectors/User | Target Latency | Max Concurrency | Expected QPS |
|----------|-------------|----------------|-----------------|-------------|
| ... | ... | ... | ... | ... |

---

## 4. Recommendations

### For Production Use
<numbered recommendations>

### For Capacity Planning (<hardware>, Parallel=<N>)
<bullet points with QPS expectations per scale>

---

## 5. Files Reference

### Scripts
| File | Description |
|------|-------------|
| ... | ... |

### Results
| Directory | Description |
|-----------|-------------|
| ... | ... |

Contents:
- <list all PNG, CSV, JSON files>

### Data
| Directory | Dim | Size | Shards |
|-----------|-----|------|--------|
| ... | ... | ... | ... |
```

### Step 5: Key rules

1. **Unified table** — All scales go in ONE table with a `Scale` column. Do NOT create separate tables per scale. Use empty separator rows between scale groups if desired.
2. **English units** — Always use 10K/100K/500K/1M, never use Chinese "w" (万) units anywhere in the report.
3. **Bold peak QPS** — Mark the peak QPS value per scale with `**bold**`.
4. **Data accuracy** — Copy numbers directly from CSV/JSON. Round to 1 decimal place for display.
5. **Comparison section** — If `BENCHMARK_REPORT.md` exists, read it to compare with prior results on different hardware or configurations.
6. **Key Findings must be data-driven** — Every claim must reference specific numbers from the results.
7. **SQL examples** — Include the actual query template used in the benchmark.
8. **Test command** — Always include the exact command in a bash code block.
