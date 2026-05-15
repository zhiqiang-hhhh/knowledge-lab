#!/usr/bin/env python3
"""
Doris Vector Search Benchmark

Tests brute-force vector search performance with user_id filter.
Generates detailed CSV results and visualization charts.

Test scenarios:
  1.  Scale test       - Fixed user, fixed LIMIT, across 4 table sizes
  2.  Top-K test       - Fixed table, varying LIMIT (1, 10, 50, 100, 500)
  3.  Filter test      - Varying number of users in WHERE clause
  4.  Distance fn test - inner_product / l2_distance / cosine_similarity
  5.  Concurrency test - Concurrent query throughput
  6.  Large Top-K test - Extended LIMIT range (100, 500, 1000, 2000, 5000)
  7.  Full scan test   - No user_id filter, brute-force across entire table
  8.  Cache effect test - Same query repeated many times, measure cache warming
  9.  Concurrent scale  - Concurrency test across different table sizes
  10. High concurrency  - Extended concurrency levels (1, 4, 8, 16, 32, 64)
"""

import os
import sys
import time
import json
import random
import argparse
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import mysql.connector
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

warnings.filterwarnings("ignore")

# ─── Configuration ───────────────────────────────────────────────
DORIS_HOST = "127.0.0.1"
DORIS_PORT = 9030
DORIS_USER = "root"
DORIS_PASS = ""
DORIS_DB   = "test_demo"

TABLES_128D = {
    "10k":  "sift_user_1w",
    "100k": "sift_user_10w",
    "500k": "sift_user_50w",
    "1m":   "sift_user_100w",
}
TABLES_128D_PQ = {
    "10k":  "sift_user_1w_pq",
    "100k": "sift_user_10w_pq",
    "500k": "sift_user_50w_pq",
    "1m":   "sift_user_100w_pq",
}
TABLES_768D = {
    "10k":  "cohere_user_1w",
    "100k": "cohere_user_10w",
    "500k": "cohere_user_50w",
    "1m":   "cohere_user_100w",
}
TABLES_768D_PQ = {
    "10k":  "cohere_user_1w_pq",
    "100k": "cohere_user_10w_pq",
    "500k": "cohere_user_50w_pq",
    "1m":   "cohere_user_100w_pq",
}

DIM_BASE_CONFIG = {
    128: {
        "label":      "128D (SIFT)",
        "base_suffix": "128d",
        "metric":     "l2_distance",
        "order":      "ASC",
        "tables": {
            "bruteforce": TABLES_128D,
            "pq_on_disk": TABLES_128D_PQ,
        },
        "query_table": {
            "bruteforce": "sift_user_1w",
            "pq_on_disk": "sift_user_1w_pq",
        },
        "distfn_functions": {
            "bruteforce": {
                "l2_distance":   ("ASC", "l2_distance(embedding, {vec})"),
                "inner_product": ("DESC", "inner_product(embedding, {vec})"),
            },
            "pq_on_disk": {
                "l2_distance_approximate": ("ASC", "l2_distance_approximate(embedding, {vec})"),
            },
        },
    },
    768: {
        "label":      "768D (Cohere)",
        "base_suffix": "768d",
        "metric":     "inner_product",
        "order":      "DESC",
        "tables": {
            "bruteforce": TABLES_768D,
            "pq_on_disk": TABLES_768D_PQ,
        },
        "query_table": {
            "bruteforce": "cohere_user_1w",
            "pq_on_disk": "cohere_user_1w_pq",
        },
        "distfn_functions": {
            "bruteforce": {
                "l2_distance":   ("ASC", "l2_distance(embedding, {vec})"),
                "inner_product": ("DESC", "inner_product(embedding, {vec})"),
            },
            "pq_on_disk": {
                "inner_product_approximate": ("DESC", "inner_product_approximate(embedding, {vec})"),
            },
        },
    },
}


def resolve_dim_conf(dim, search_mode):
    base = DIM_BASE_CONFIG[dim]
    metric = base["metric"]
    dist_fn = metric if search_mode == "bruteforce" else f"{metric}_approximate"
    suffix = base["base_suffix"] if search_mode == "bruteforce" else f"{base['base_suffix']}_{search_mode}"
    return {
        "tables": base["tables"][search_mode],
        "dist_fn": dist_fn,
        "order": base["order"],
        "query_table": base["query_table"][search_mode],
        "label": base["label"],
        "suffix": suffix,
        "search_mode": search_mode,
        "metric": metric,
        "distfn_functions": base["distfn_functions"][search_mode],
    }

# Back-compat: default TABLES alias (overridden at runtime)
TABLES = TABLES_128D

WARMUP_RUNS  = 2
BENCH_RUNS   = 10   # iterations per test case
NUM_QUERIES  = 5    # different query vectors to average over
RECALL_MIN_QUERIES = 20
SEED         = 42
OUTPUT_DIR   = "benchmark_results"
USER_MODE    = "fixed"
FIXED_USER_ID = 42
TOTAL_USERS  = 100

# Session variables to SET on each new connection (populated by --parallel etc.)
SESSION_VARS = {}

# ─── Helpers ─────────────────────────────────────────────────────

def get_conn(apply_session_vars=True):
    conn = mysql.connector.connect(
        host=DORIS_HOST, port=DORIS_PORT,
        user=DORIS_USER, password=DORIS_PASS,
        database=DORIS_DB, autocommit=True,
    )
    if apply_session_vars and SESSION_VARS:
        cur = conn.cursor()
        try:
            for k, v in SESSION_VARS.items():
                cur.execute(f"SET {k} = {v}")
        finally:
            cur.close()
    return conn


def benchmark_user_label(user_mode=None, fixed_user_id=None):
    """Human-readable label for the current user filter mode."""
    mode = USER_MODE if user_mode is None else user_mode
    uid = FIXED_USER_ID if fixed_user_id is None else fixed_user_id
    return f"user_id={uid}" if mode == "fixed" else "user_id=query-specific"


def query_user_id(query_item):
    """Resolve the user_id tied to a sampled query vector."""
    if isinstance(query_item, dict):
        return int(query_item["user_id"])
    return FIXED_USER_ID


def query_vector(query_item):
    """Return the embedding payload from a sampled query item."""
    if isinstance(query_item, dict):
        return query_item["embedding"]
    return query_item


def single_user_where(query_item):
    """WHERE clause for single-user benchmarks."""
    user_id = FIXED_USER_ID if USER_MODE == "fixed" else query_user_id(query_item)
    return f"user_id = {user_id}"


def filter_where_clause(n_users, query_item):
    """WHERE clause for filter-selectivity benchmarks."""
    anchor_user_id = FIXED_USER_ID if USER_MODE == "fixed" else query_user_id(query_item)
    if n_users <= 1:
        return f"user_id = {anchor_user_id}"

    other_user_ids = [uid for uid in range(TOTAL_USERS) if uid != anchor_user_id]
    rng = random.Random(SEED * 1000 + n_users * 100 + anchor_user_id)
    sampled = [anchor_user_id] + rng.sample(other_user_ids, n_users - 1)
    return f"user_id IN ({','.join(map(str, sorted(sampled)))})"


def add_run_metadata(stats):
    """Attach common run metadata to a result row."""
    stats["user_mode"] = USER_MODE
    stats["user_label"] = benchmark_user_label()
    return stats


def dataframe_user_label(df):
    """Get a display label from a result DataFrame, with legacy fallback."""
    if "user_label" in df.columns and not df.empty:
        return df["user_label"].iloc[0]
    return benchmark_user_label("fixed", 42)


def table_exists(conn, table_name):
    """Check whether a table exists in the active Doris database."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1",
            (DORIS_DB, table_name),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()


def load_query_vectors(dim_conf, n=None, seed=SEED):
    """Pick n random embedding vectors from an available source table."""
    if n is None:
        n = NUM_QUERIES
    conn = get_conn()
    rng = random.Random(seed)
    candidate_tables = [dim_conf["query_table"]]
    candidate_tables.extend(dim_conf["tables"].values())
    candidate_tables = list(dict.fromkeys(candidate_tables))
    try:
        for query_table in candidate_tables:
            if not table_exists(conn, query_table):
                print(f"Query source table {query_table} not found, trying next candidate...")
                continue

            vectors = []
            cur = conn.cursor()
            try:
                attempts = 0
                max_attempts = max(n * 20, 100)
                while len(vectors) < n and attempts < max_attempts:
                    uid = rng.randrange(TOTAL_USERS)
                    eid = rng.randint(0, 9999)
                    cur.execute(
                        f"SELECT embedding FROM {query_table} "
                        f"WHERE user_id={uid} AND id={eid} LIMIT 1"
                    )
                    row = cur.fetchone()
                    attempts += 1
                    if row:
                        vectors.append({
                            "user_id": uid,
                            "id": eid,
                            "embedding": row[0],
                        })
            finally:
                cur.close()

            print(f"Loaded {len(vectors)} query vectors from {query_table}")
            if vectors:
                return vectors
    finally:
        conn.close()

    raise RuntimeError(
        "No query vectors loaded. Tried source tables: "
        f"{candidate_tables}. Please ensure at least one source table exists and contains data."
    )


def format_vec(vec_str):
    """Ensure vector string is in [v1,v2,...] format."""
    v = str(vec_str).strip()
    if not v.startswith("["):
        v = "[" + v + "]"
    return v


def vector_param():
    """Prepared-statement placeholder for Doris array<float> query vectors."""
    return "CAST(%s AS ARRAY<FLOAT>)"


def run_query(conn, sql, params=None):
    """Execute a query and return (latency_seconds, row_count)."""
    t0 = time.perf_counter()
    cur = conn.cursor(prepared=params is not None)
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()
    elapsed = time.perf_counter() - t0
    return elapsed, len(rows)


def run_query_rows(conn, sql, params=None):
    """Execute a query and return (latency_seconds, rows)."""
    t0 = time.perf_counter()
    cur = conn.cursor(prepared=params is not None)
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()
    elapsed = time.perf_counter() - t0
    return elapsed, rows


def percentile(data, p):
    """Calculate p-th percentile."""
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_d) else f
    return sorted_d[f] + (k - f) * (sorted_d[c] - sorted_d[f])


def recall_at_k(exact_ids, approx_ids):
    """Compute recall@k based on ID overlap."""
    if not exact_ids:
        return 0.0
    return len(set(exact_ids) & set(approx_ids)) / len(exact_ids)


def ensure_min_recall_queries(query_vecs, dim_conf, minimum=RECALL_MIN_QUERIES):
    """Use enough query vectors to reduce recall variance."""
    if len(query_vecs) >= minimum:
        return query_vecs
    print(f"  Recall uses {len(query_vecs)} queries; reloading {minimum} queries for a stabler estimate")
    return load_query_vectors(dim_conf, n=minimum, seed=SEED + minimum)


def recall_summary_stats(recalls):
    """Summarize per-query recall values."""
    values = np.array(recalls, dtype=float)
    return {
        "avg_recall": round(float(values.mean()), 4),
        "min_recall": round(float(values.min()), 4),
        "max_recall": round(float(values.max()), 4),
        "std_recall": round(float(values.std()), 4),
        "p10_recall": round(float(np.percentile(values, 10)), 4),
        "p90_recall": round(float(np.percentile(values, 90)), 4),
    }


def run_bench(conn, sql_template, query_vecs, warmup=None, runs=None):
    """Run benchmark for a SQL template with a prepared vector parameter.

    Returns dict with timing stats (in milliseconds).
    """
    if warmup is None:
        warmup = WARMUP_RUNS
    if runs is None:
        runs = BENCH_RUNS

    latencies = []

    for qi, qv in enumerate(query_vecs):
        sql = sql_template(qv) if callable(sql_template) else sql_template
        vec = format_vec(query_vector(qv))
        params = (vec,)

        # warmup
        for _ in range(warmup):
            run_query(conn, sql, params)

        # bench
        for _ in range(runs):
            elapsed, _ = run_query(conn, sql, params)
            latencies.append(elapsed * 1000)  # ms

    return {
        "avg_ms":  round(np.mean(latencies), 2),
        "p50_ms":  round(percentile(latencies, 50), 2),
        "p90_ms":  round(percentile(latencies, 90), 2),
        "p99_ms":  round(percentile(latencies, 99), 2),
        "min_ms":  round(min(latencies), 2),
        "max_ms":  round(max(latencies), 2),
        "std_ms":  round(np.std(latencies), 2),
        "runs":    len(latencies),
    }


# ─── Test Scenarios ──────────────────────────────────────────────

def test_scale(conn, query_vecs, dim_conf):
    """Scenario 1: Same query across different table sizes."""
    tables = dim_conf["tables"]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_label = benchmark_user_label()

    print("\n" + "=" * 60)
    print(f"Scenario 1: Scale Test [{dim_conf['label']}] ({user_label}, LIMIT 10)")
    print("  How does latency change with per-user data volume?")
    print("=" * 60)

    results = []
    for label, table in tables.items():
        sql = lambda qv, table=table: (
            f"SELECT id FROM {table} "
            f"WHERE {single_user_where(qv)} "
            f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
            f"LIMIT 10"
        )
        print(f"  Testing {table} ({label}/user)...", end="", flush=True)
        stats = add_run_metadata(run_bench(conn, sql, query_vecs))
        stats["table"] = table
        stats["scale"] = label
        stats["dist_fn"] = dist_fn
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_topk(conn, query_vecs, dim_conf, table_key="10w"):
    """Scenario 2: Varying LIMIT (Top-K)."""
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    limits = [1, 10, 50, 100, 500]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 2: Top-K Test [{dim_conf['label']}] on {table} ({user_label})")
    print(f"  How does LIMIT K affect latency?")
    print(f"{'=' * 60}")

    results = []
    for k in limits:
        sql = lambda qv, table=table, k=k: (
            f"SELECT id FROM {table} "
            f"WHERE {single_user_where(qv)} "
            f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
            f"LIMIT {k}"
        )
        print(f"  LIMIT {k:>4d}...", end="", flush=True)
        stats = add_run_metadata(run_bench(conn, sql, query_vecs))
        stats["table"] = table
        stats["limit_k"] = k
        stats["dist_fn"] = dist_fn
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_filter(conn, query_vecs, dim_conf, table_key="10w"):
    """Scenario 3: Varying filter selectivity (number of users)."""
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_counts = [1, 5, 10, 50, 100]

    print(f"\n{'=' * 60}")
    print(f"Scenario 3: Filter Selectivity Test [{dim_conf['label']}] on {table} (LIMIT 10)")
    print(f"  How does scanning more users affect latency?")
    print(f"{'=' * 60}")

    user_label = benchmark_user_label()

    results = []
    for n_users in user_counts:
        sql = lambda qv, table=table, n_users=n_users: (
            f"SELECT id FROM {table} "
            f"WHERE {filter_where_clause(n_users, qv)} "
            f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
            f"LIMIT 10"
        )
        print(f"  {n_users:>3d} users...", end="", flush=True)
        stats = add_run_metadata(run_bench(conn, sql, query_vecs))
        stats["table"] = table
        stats["n_users"] = n_users
        stats["dist_fn"] = dist_fn
        stats["filter_anchor"] = user_label
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_distance_fn(conn, query_vecs, dim_conf, table_key="10w"):
    """Scenario 4: Compare different distance/similarity functions."""
    table = dim_conf["tables"][table_key]
    functions = dim_conf["distfn_functions"]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 4: Distance Function Test [{dim_conf['label']}] on {table} ({user_label}, LIMIT 10)")
    print(f"  Comparing: {' / '.join(functions.keys())}")
    print(f"{'=' * 60}")

    results = []
    for fn_name, (order, expr) in functions.items():
        sql = lambda qv, table=table, order=order, expr=expr: (
            f"SELECT id FROM {table} "
            f"WHERE {single_user_where(qv)} "
            f"ORDER BY {expr.format(vec=vector_param())} {order} "
            f"LIMIT 10"
        )
        print(f"  {fn_name:>20s}...", end="", flush=True)
        stats = add_run_metadata(run_bench(conn, sql, query_vecs))
        stats["table"] = table
        stats["function"] = fn_name
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_concurrency(query_vecs, dim_conf, table_key="10w", concurrency_levels=None):
    """Scenario 5: Concurrent query throughput."""
    if concurrency_levels is None:
        concurrency_levels = [1, 2, 4, 8, 16]
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 5: Concurrency Test [{dim_conf['label']}] on {table} ({user_label}, LIMIT 10)")
    print(f"  Measuring throughput at different concurrency levels")
    print(f"{'=' * 60}")

    def worker(query_item, n_queries=20):
        """Each worker runs n_queries and returns total latency."""
        c = get_conn()
        vec = format_vec(query_vector(query_item))
        sql = (f"SELECT id FROM {table} "
               f"WHERE {single_user_where(query_item)} "
               f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
               f"LIMIT 10")
        latencies = []
        for _ in range(n_queries):
            elapsed, _ = run_query(c, sql, (vec,))
            latencies.append(elapsed * 1000)
        c.close()
        return latencies

    results = []
    for c_level in concurrency_levels:
        queries_per_worker = max(10, 40 // c_level)
        warmup_query = query_vecs[0]
        vec = format_vec(query_vector(warmup_query))

        # Warmup
        wconn = get_conn()
        sql_w = (f"SELECT id FROM {table} "
                 f"WHERE {single_user_where(warmup_query)} "
                 f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
                 f"LIMIT 10")
        for _ in range(3):
            run_query(wconn, sql_w, (vec,))
        wconn.close()

        t0 = time.perf_counter()
        all_latencies = []
        with ThreadPoolExecutor(max_workers=c_level) as pool:
            futures = [pool.submit(worker, query_vecs[i % len(query_vecs)], queries_per_worker)
                       for i in range(c_level)]
            for f in as_completed(futures):
                all_latencies.extend(f.result())
        wall_time = time.perf_counter() - t0

        total_queries = len(all_latencies)
        qps = total_queries / wall_time

        stats = {
            "concurrency":  c_level,
            "table":        table,
            "dist_fn":      dist_fn,
            "search_mode":  dim_conf["search_mode"],
            "total_queries": total_queries,
            "wall_time_s":  round(wall_time, 2),
            "qps":          round(qps, 1),
            "avg_ms":       round(np.mean(all_latencies), 2),
            "p50_ms":       round(percentile(all_latencies, 50), 2),
            "p90_ms":       round(percentile(all_latencies, 90), 2),
            "p99_ms":       round(percentile(all_latencies, 99), 2),
        }
        add_run_metadata(stats)
        results.append(stats)
        print(f"  C={c_level:>2d}  QPS={qps:>7.1f}  avg={stats['avg_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_large_topk(conn, query_vecs, dim_conf, table_key="10w"):
    """Scenario 6: Extended Top-K range to test sorting overhead."""
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    limits = [100, 500, 1000, 2000, 5000]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 6: Large Top-K Test [{dim_conf['label']}] on {table} ({user_label})")
    print(f"  How does very large LIMIT affect latency?")
    print(f"{'=' * 60}")

    results = []
    for k in limits:
        sql = lambda qv, table=table, k=k: (
            f"SELECT id FROM {table} "
            f"WHERE {single_user_where(qv)} "
            f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
            f"LIMIT {k}"
        )
        print(f"  LIMIT {k:>5d}...", end="", flush=True)
        stats = add_run_metadata(run_bench(conn, sql, query_vecs))
        stats["table"] = table
        stats["limit_k"] = k
        stats["dist_fn"] = dist_fn
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_full_scan(conn, query_vecs, dim_conf):
    """Scenario 7: No user_id filter - full table brute-force scan."""
    tables = dim_conf["tables"]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]

    print(f"\n{'=' * 60}")
    print(f"Scenario 7: Full Scan Test [{dim_conf['label']}] (no user_id filter, LIMIT 10)")
    print(f"  How expensive is scanning ALL users?")
    print(f"{'=' * 60}")

    results = []
    for label, table in tables.items():
        sql = (f"SELECT user_id, id FROM {table} "
               f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
               f"LIMIT 10")
        print(f"  Full scan {table} ({label})...", end="", flush=True)
        stats = run_bench(conn, sql, query_vecs, warmup=1, runs=5)
        stats["table"] = table
        stats["scale"] = label
        stats["dist_fn"] = dist_fn
        stats["search_mode"] = dim_conf["search_mode"]
        results.append(stats)
        print(f"  avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_cache_effect(conn, query_vecs, dim_conf, table_key="10w"):
    """Scenario 8: Repeated identical query to measure cache warming."""
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    total_iterations = 50
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 8: Cache Effect Test [{dim_conf['label']}] on {table}")
    print(f"  Running same query {total_iterations} times, no warmup")
    print(f"{'=' * 60}")

    cache_query = query_vecs[0]
    vec = format_vec(query_vector(cache_query))
    sql = (f"SELECT id FROM {table} "
           f"WHERE {single_user_where(cache_query)} "
           f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
           f"LIMIT 10")

    latencies = []
    for i in range(total_iterations):
        elapsed, _ = run_query(conn, sql, (vec,))
        latencies.append(elapsed * 1000)

    # Group into windows of 5 to show progression
    window = 5
    results = []
    for start in range(0, total_iterations, window):
        chunk = latencies[start:start + window]
        results.append({
            "iteration_start": start + 1,
            "iteration_end": min(start + window, total_iterations),
            "table": table,
            "dist_fn": dist_fn,
            "search_mode": dim_conf["search_mode"],
            "user_mode": USER_MODE,
            "user_label": user_label,
            "avg_ms": round(np.mean(chunk), 2),
            "min_ms": round(min(chunk), 2),
            "max_ms": round(max(chunk), 2),
        })

    for r in results:
        print(f"  Iter {r['iteration_start']:>2d}-{r['iteration_end']:>2d}: "
              f"avg={r['avg_ms']:.1f}ms  min={r['min_ms']:.1f}ms  max={r['max_ms']:.1f}ms")

    # Also return the raw per-iteration data for charting
    raw_df = pd.DataFrame({
        "iteration": list(range(1, total_iterations + 1)),
        "latency_ms": [round(x, 2) for x in latencies],
        "table": table,
        "dist_fn": dist_fn,
        "search_mode": dim_conf["search_mode"],
        "user_mode": USER_MODE,
        "user_label": user_label,
    })
    return pd.DataFrame(results), raw_df


def test_concurrent_scale(query_vecs, dim_conf, concurrency_levels=None, duration=30, limit=10):
    """Scenario 9: Duration-based concurrent scale test.

    For every (table_scale x concurrency_level) combination, run queries for
    *duration* seconds and measure QPS / P50 / P90 / P99.
    """
    import threading

    if concurrency_levels is None:
        concurrency_levels = [1, 4, 8, 16, 32]

    tables = dim_conf["tables"]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 9: Concurrent Scale Test [{dim_conf['label']}]")
    print(f"  Concurrency levels: {concurrency_levels}")
    print(f"  Duration per case : {duration}s")
    print(f"  Query: WHERE {user_label} ORDER BY {dist_fn}(...) {order} LIMIT {limit}")
    print(f"{'=' * 60}")

    def worker(table, query_item, stop_event):
        """Run queries in a loop until stop_event is set."""
        c = get_conn()
        vec = format_vec(query_vector(query_item))
        sql = (f"SELECT id FROM {table} "
               f"WHERE {single_user_where(query_item)} "
               f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
               f"LIMIT {limit}")
        latencies = []
        while not stop_event.is_set():
            try:
                elapsed, _ = run_query(c, sql, (vec,))
                latencies.append(elapsed * 1000)
            except Exception:
                # Reconnect on error and continue
                try:
                    c.close()
                except Exception:
                    pass
                c = get_conn()
        try:
            c.close()
        except Exception:
            pass
        return latencies

    results = []
    for label, table in tables.items():
        # Warmup once per table
        wconn = get_conn()
        warmup_query = query_vecs[0]
        vec = format_vec(query_vector(warmup_query))
        sql_w = (f"SELECT id FROM {table} "
                 f"WHERE {single_user_where(warmup_query)} "
                 f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
                 f"LIMIT {limit}")
        for _ in range(3):
            run_query(wconn, sql_w, (vec,))
        wconn.close()

        for c_level in concurrency_levels:
            stop_event = threading.Event()
            t0 = time.perf_counter()
            all_latencies = []

            with ThreadPoolExecutor(max_workers=c_level) as pool:
                futures = [
                    pool.submit(worker, table, query_vecs[i % len(query_vecs)], stop_event)
                    for i in range(c_level)
                ]
                # Let it run for the specified duration
                time.sleep(duration)
                stop_event.set()

                for f in as_completed(futures):
                    all_latencies.extend(f.result())

            wall_time = time.perf_counter() - t0
            total_queries = len(all_latencies)
            qps = total_queries / wall_time if wall_time > 0 else 0

            stats = {
                "scale":         label,
                "table":         table,
                "concurrency":   c_level,
                "limit":         limit,
                "dist_fn":       dist_fn,
                "search_mode":   dim_conf["search_mode"],
                "duration_s":    duration,
                "total_queries": total_queries,
                "wall_time_s":   round(wall_time, 2),
                "qps":           round(qps, 1),
                "avg_ms":        round(np.mean(all_latencies), 2) if all_latencies else 0,
                "p50_ms":        round(percentile(all_latencies, 50), 2) if all_latencies else 0,
                "p90_ms":        round(percentile(all_latencies, 90), 2) if all_latencies else 0,
                "p99_ms":        round(percentile(all_latencies, 99), 2) if all_latencies else 0,
            }
            add_run_metadata(stats)
            results.append(stats)
            print(f"  {table:>20s}  C={c_level:<3d}  QPS={qps:>7.1f}  "
                  f"avg={stats['avg_ms']:.1f}ms  p50={stats['p50_ms']:.1f}ms  "
                  f"p90={stats['p90_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms  "
                  f"({total_queries} queries in {wall_time:.1f}s)")

    return pd.DataFrame(results)


def test_high_concurrency(query_vecs, dim_conf, table_key="10w", concurrency_levels=None):
    """Scenario 10: Extended concurrency levels."""
    if concurrency_levels is None:
        concurrency_levels = [1, 4, 8, 16, 32, 64]
    table = dim_conf["tables"][table_key]
    dist_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 10: High Concurrency Test [{dim_conf['label']}] on {table} (LIMIT 10)")
    print(f"  Extended concurrency levels: {concurrency_levels}")
    print(f"{'=' * 60}")

    def worker(query_item, n_queries=20):
        c = get_conn()
        vec = format_vec(query_vector(query_item))
        sql = (f"SELECT id FROM {table} "
               f"WHERE {single_user_where(query_item)} "
               f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
               f"LIMIT 10")
        latencies = []
        for _ in range(n_queries):
            elapsed, _ = run_query(c, sql, (vec,))
            latencies.append(elapsed * 1000)
        c.close()
        return latencies

    results = []
    for c_level in concurrency_levels:
        queries_per_worker = max(10, 60 // c_level)
        warmup_query = query_vecs[0]
        vec = format_vec(query_vector(warmup_query))

        # Warmup
        wconn = get_conn()
        sql_w = (f"SELECT id FROM {table} "
                 f"WHERE {single_user_where(warmup_query)} "
                 f"ORDER BY {dist_fn}(embedding, {vector_param()}) {order} "
                 f"LIMIT 10")
        for _ in range(3):
            run_query(wconn, sql_w, (vec,))
        wconn.close()

        t0 = time.perf_counter()
        all_latencies = []
        with ThreadPoolExecutor(max_workers=c_level) as pool:
            futures = [pool.submit(worker, query_vecs[i % len(query_vecs)], queries_per_worker)
                       for i in range(c_level)]
            for f in as_completed(futures):
                all_latencies.extend(f.result())
        wall_time = time.perf_counter() - t0

        total_queries = len(all_latencies)
        qps = total_queries / wall_time
        stats = {
            "concurrency":   c_level,
            "table":         table,
            "dist_fn":       dist_fn,
            "search_mode":   dim_conf["search_mode"],
            "total_queries": total_queries,
            "wall_time_s":   round(wall_time, 2),
            "qps":           round(qps, 1),
            "avg_ms":        round(np.mean(all_latencies), 2),
            "p50_ms":        round(percentile(all_latencies, 50), 2),
            "p90_ms":        round(percentile(all_latencies, 90), 2),
            "p99_ms":        round(percentile(all_latencies, 99), 2),
        }
        add_run_metadata(stats)
        results.append(stats)
        print(f"  C={c_level:>2d}  QPS={qps:>7.1f}  avg={stats['avg_ms']:.1f}ms  p99={stats['p99_ms']:.1f}ms")

    return pd.DataFrame(results)


def test_recall(query_vecs, dim_conf, table_key="10w", recall_ks=None):
    """PQ mode only: compare approximate results against brute-force ground truth."""
    if dim_conf["search_mode"] != "pq_on_disk":
        return pd.DataFrame()

    if recall_ks is None:
        recall_ks = [10, 100]

    if not query_vecs:
        raise RuntimeError("Recall test requires at least one query vector")

    query_vecs = ensure_min_recall_queries(query_vecs, dim_conf)
    table = dim_conf["tables"][table_key]
    exact_fn = dim_conf["metric"]
    approx_fn = dim_conf["dist_fn"]
    order = dim_conf["order"]
    user_label = benchmark_user_label()

    print(f"\n{'=' * 60}")
    print(f"Scenario 11: Recall Test [{dim_conf['label']}] on {table} ({user_label})")
    print(f"  Comparing {approx_fn} against exact {exact_fn} on the same table")
    print(f"{'=' * 60}")

    exact_conn = get_conn(apply_session_vars=False)
    approx_conn = get_conn(apply_session_vars=False)
    results = []
    try:
        for k in recall_ks:
            recalls = []
            exact_lat = []
            approx_lat = []
            for qv in query_vecs:
                vec = format_vec(query_vector(qv))
                exact_sql = (
                    f"SELECT id FROM {table} "
                    f"WHERE {single_user_where(qv)} "
                    f"ORDER BY {exact_fn}(embedding, {vector_param()}) {order} "
                    f"LIMIT {k}"
                )
                approx_sql = (
                    f"SELECT id FROM {table} "
                    f"WHERE {single_user_where(qv)} "
                    f"ORDER BY {approx_fn}(embedding, {vector_param()}) {order} "
                    f"LIMIT {k}"
                )
                params = (vec,)
                elapsed_exact, exact_rows = run_query_rows(exact_conn, exact_sql, params)
                elapsed_approx, approx_rows = run_query_rows(approx_conn, approx_sql, params)
                exact_ids = [r[0] for r in exact_rows]
                approx_ids = [r[0] for r in approx_rows]
                recalls.append(recall_at_k(exact_ids, approx_ids))
                exact_lat.append(elapsed_exact * 1000)
                approx_lat.append(elapsed_approx * 1000)

            stats = {
                "table": table,
                "limit_k": k,
                "dist_fn": approx_fn,
                "exact_dist_fn": exact_fn,
                "search_mode": dim_conf["search_mode"],
                "avg_exact_ms": round(float(np.mean(exact_lat)), 2),
                "avg_approx_ms": round(float(np.mean(approx_lat)), 2),
                "speedup": round(float(np.mean(exact_lat)) / max(float(np.mean(approx_lat)), 1e-9), 2),
                "queries": len(query_vecs),
            }
            stats.update(recall_summary_stats(recalls))
            add_run_metadata(stats)
            results.append(stats)
            print(f"  LIMIT {k:>4d}  recall={stats['avg_recall']:.4f}  "
                  f"p10={stats['p10_recall']:.4f}  p90={stats['p90_recall']:.4f}  "
                  f"exact={stats['avg_exact_ms']:.1f}ms  approx={stats['avg_approx_ms']:.1f}ms  "
                  f"speedup={stats['speedup']:.2f}x")
    finally:
        exact_conn.close()
        approx_conn.close()

    return pd.DataFrame(results)


# ─── Visualization ───────────────────────────────────────────────

def setup_plot_style():
    plt.rcParams.update({
        "figure.figsize": (10, 6),
        "figure.dpi": 150,
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def plot_scale(df, output_dir, dist_fn="l2_distance"):
    """Bar chart: latency across table sizes."""
    fig, ax = plt.subplots()
    x = np.arange(len(df))
    width = 0.25

    ax.bar(x - width, df["p50_ms"], width, label="P50", color="#4C72B0")
    ax.bar(x,         df["avg_ms"], width, label="Avg", color="#55A868")
    ax.bar(x + width, df["p99_ms"], width, label="P99", color="#C44E52")

    ax.set_xlabel("Vectors per User")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 1: Latency vs Data Scale\n({dataframe_user_label(df)}, LIMIT 10, {dist_fn})")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scale"])
    ax.legend()

    for i, row in df.iterrows():
        ax.text(i, row["p99_ms"] + 1, f'{row["p99_ms"]:.0f}', ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    path = os.path.join(output_dir, "01_scale_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_topk(df, output_dir, dist_fn="l2_distance"):
    """Line chart: latency vs LIMIT K."""
    fig, ax = plt.subplots()

    ax.plot(df["limit_k"], df["avg_ms"], "o-", label="Avg", color="#55A868", linewidth=2)
    ax.plot(df["limit_k"], df["p50_ms"], "s--", label="P50", color="#4C72B0")
    ax.plot(df["limit_k"], df["p99_ms"], "^--", label="P99", color="#C44E52")

    ax.set_xlabel("Top-K (LIMIT)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 2: Latency vs Top-K\n({df['table'].iloc[0]}, {dataframe_user_label(df)}, {dist_fn})")
    ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, "02_topk_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_filter(df, output_dir, dist_fn="l2_distance"):
    """Bar chart: latency vs number of users in filter."""
    fig, ax = plt.subplots()
    x = np.arange(len(df))
    width = 0.25

    ax.bar(x - width, df["p50_ms"], width, label="P50", color="#4C72B0")
    ax.bar(x,         df["avg_ms"], width, label="Avg", color="#55A868")
    ax.bar(x + width, df["p99_ms"], width, label="P99", color="#C44E52")

    ax.set_xlabel("Number of Users in Filter")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 3: Latency vs Filter Selectivity\n({df['table'].iloc[0]}, LIMIT 10, {dist_fn})")
    ax.set_xticks(x)
    ax.set_xticklabels(df["n_users"])
    ax.legend()

    for i, row in df.iterrows():
        ax.text(i, row["p99_ms"] + 1, f'{row["p99_ms"]:.0f}', ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    path = os.path.join(output_dir, "03_filter_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_distance_fn(df, output_dir):
    """Horizontal bar chart: comparing distance functions."""
    fig, ax = plt.subplots(figsize=(10, 5))

    y = np.arange(len(df))
    height = 0.25

    ax.barh(y - height, df["p50_ms"], height, label="P50", color="#4C72B0")
    ax.barh(y,          df["avg_ms"], height, label="Avg", color="#55A868")
    ax.barh(y + height, df["p99_ms"], height, label="P99", color="#C44E52")

    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Distance Function")
    ax.set_title(f"Scenario 4: Distance Function Comparison\n({df['table'].iloc[0]}, {dataframe_user_label(df)}, LIMIT 10)")
    ax.set_yticks(y)
    ax.set_yticklabels(df["function"])
    ax.legend()

    for i, row in df.iterrows():
        ax.text(row["p99_ms"] + 0.5, i + height, f'{row["p99_ms"]:.0f}', va="center", fontsize=9)

    plt.tight_layout()
    path = os.path.join(output_dir, "04_distance_fn_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_concurrency(df, output_dir, dist_fn="l2_distance"):
    """Dual-axis chart: QPS and P99 vs concurrency."""
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()

    x = df["concurrency"]
    ax1.bar(x, df["qps"], width=0.6, alpha=0.7, color="#4C72B0", label="QPS")
    ax2.plot(x, df["p99_ms"], "o-", color="#C44E52", linewidth=2, markersize=8, label="P99 Latency")
    ax2.plot(x, df["avg_ms"], "s--", color="#55A868", linewidth=2, markersize=6, label="Avg Latency")

    ax1.set_xlabel("Concurrency")
    ax1.set_ylabel("QPS", color="#4C72B0")
    ax2.set_ylabel("Latency (ms)", color="#C44E52")
    ax1.set_title(f"Scenario 5: Concurrency Test\n({df['table'].iloc[0]}, {dataframe_user_label(df)}, LIMIT 10, {dist_fn})")
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    path = os.path.join(output_dir, "05_concurrency_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_large_topk(df, output_dir, dist_fn="l2_distance"):
    """Line chart: latency vs large LIMIT K values."""
    fig, ax = plt.subplots()

    ax.plot(df["limit_k"], df["avg_ms"], "o-", label="Avg", color="#55A868", linewidth=2)
    ax.plot(df["limit_k"], df["p50_ms"], "s--", label="P50", color="#4C72B0")
    ax.plot(df["limit_k"], df["p99_ms"], "^--", label="P99", color="#C44E52")

    ax.set_xlabel("Top-K (LIMIT)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 6: Large Top-K Test\n({df['table'].iloc[0]}, {dataframe_user_label(df)}, {dist_fn})")
    ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, "06_large_topk_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_full_scan(df, output_dir, dist_fn="l2_distance"):
    """Bar chart: full scan latency across table sizes."""
    fig, ax = plt.subplots()
    x = np.arange(len(df))
    width = 0.25

    ax.bar(x - width, df["p50_ms"], width, label="P50", color="#4C72B0")
    ax.bar(x,         df["avg_ms"], width, label="Avg", color="#55A868")
    ax.bar(x + width, df["p99_ms"], width, label="P99", color="#C44E52")

    ax.set_xlabel("Total Rows in Table")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 7: Full Table Scan (no user_id filter)\n(LIMIT 10, {dist_fn})")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scale"])
    ax.legend()

    for i, row in df.iterrows():
        ax.text(i, row["p99_ms"] * 1.02, f'{row["p99_ms"]:.0f}', ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    path = os.path.join(output_dir, "07_full_scan_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_cache_effect(raw_df, output_dir):
    """Line chart: per-iteration latency showing cache warming."""
    fig, ax = plt.subplots()

    ax.plot(raw_df["iteration"], raw_df["latency_ms"], "o-", markersize=4,
            color="#4C72B0", linewidth=1.5, alpha=0.8)

    # Add a rolling average line
    if len(raw_df) >= 5:
        rolling = raw_df["latency_ms"].rolling(window=5, min_periods=1).mean()
        ax.plot(raw_df["iteration"], rolling, "-", color="#C44E52",
                linewidth=2.5, label="5-point rolling avg")

    ax.set_xlabel("Iteration")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"Scenario 8: Cache Effect Test\n({raw_df['table'].iloc[0]}, {dataframe_user_label(raw_df)}, LIMIT 10)")
    ax.legend()

    plt.tight_layout()
    path = os.path.join(output_dir, "08_cache_effect_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_concurrent_scale(df, output_dir, dist_fn="l2_distance"):
    """Multi-panel chart: QPS and latency across table sizes x concurrency levels.

    Generates two charts:
      09a - QPS grouped bar chart (scales on x-axis, one bar group per concurrency)
      09b - P50/P90/P99 latency heatmap-style line chart per concurrency
    """
    concurrency_levels = sorted(df["concurrency"].unique())
    scales = list(dict.fromkeys(df["scale"]))  # preserve order
    dur = df["duration_s"].iloc[0] if "duration_s" in df.columns else "?"

    # ── Chart 09a: QPS grouped bar ──
    fig, ax = plt.subplots(figsize=(12, 6))
    n_scales = len(scales)
    n_conc = len(concurrency_levels)
    bar_width = 0.8 / n_conc
    cmap = matplotlib.colormaps.get_cmap("Set2")  # type: ignore
    colors = [cmap(i / max(n_conc - 1, 1)) for i in range(n_conc)]

    for i, c_level in enumerate(concurrency_levels):
        sub = df[df["concurrency"] == c_level]
        x = np.arange(n_scales) + i * bar_width
        qps_vals = [sub[sub["scale"] == s]["qps"].values[0] if len(sub[sub["scale"] == s]) else 0
                     for s in scales]
        bars = ax.bar(x, qps_vals, width=bar_width, alpha=0.85, color=colors[i],
                       label=f"C={c_level}")
        # Value labels on bars
        for bar, val in zip(bars, qps_vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                        f"{val:.0f}", ha="center", va="bottom", fontsize=7)

    ax.set_xlabel("Table Scale")
    ax.set_ylabel("QPS")
    ax.set_title(f"Scenario 9: Concurrent Scale Test — QPS\n"
                 f"({dataframe_user_label(df)}, LIMIT 10, {dist_fn}, {dur}s per case)")
    ax.set_xticks(np.arange(n_scales) + bar_width * (n_conc - 1) / 2)
    ax.set_xticklabels(scales)
    ax.legend(title="Concurrency")
    plt.tight_layout()
    path_a = os.path.join(output_dir, "09a_concurrent_scale_qps.png")
    fig.savefig(path_a)
    plt.close(fig)
    print(f"  Saved {path_a}")

    # ── Chart 09b: Latency (P50/P90/P99) per scale, one subplot per concurrency ──
    n_cols = min(3, n_conc)
    n_rows = (n_conc + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows), squeeze=False)
    for idx, c_level in enumerate(concurrency_levels):
        r, c_idx = divmod(idx, n_cols)
        ax = axes[r][c_idx]
        sub = df[df["concurrency"] == c_level].set_index("scale").reindex(scales)
        x = np.arange(len(scales))
        ax.plot(x, sub["p50_ms"], "o-", label="P50", linewidth=2, markersize=6)
        ax.plot(x, sub["p90_ms"], "s-", label="P90", linewidth=2, markersize=6)
        ax.plot(x, sub["p99_ms"], "^-", label="P99", linewidth=2, markersize=6)
        ax.plot(x, sub["avg_ms"], "d--", label="Avg", linewidth=1.5, markersize=5, alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(scales, fontsize=9)
        ax.set_ylabel("Latency (ms)")
        ax.set_title(f"C={c_level}")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    # Hide empty subplots
    for idx in range(n_conc, n_rows * n_cols):
        r, c_idx = divmod(idx, n_cols)
        axes[r][c_idx].set_visible(False)

    fig.suptitle(f"Scenario 9: Concurrent Scale Test — Latency\n"
                 f"({dataframe_user_label(df)}, LIMIT 10, {dist_fn}, {dur}s per case)", fontsize=13)
    plt.tight_layout()
    path_b = os.path.join(output_dir, "09b_concurrent_scale_latency.png")
    fig.savefig(path_b)
    plt.close(fig)
    print(f"  Saved {path_b}")

    # ── Also keep a combined 09_ for backward compat ──
    path_c = os.path.join(output_dir, "09_concurrent_scale_test.png")
    # Re-create the QPS chart as the main one
    import shutil
    shutil.copy2(path_a, path_c)
    print(f"  Saved {path_c}")


def plot_high_concurrency(df, output_dir, dist_fn="l2_distance"):
    """Dual-axis chart: QPS and latency vs extended concurrency."""
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()

    x = df["concurrency"]
    ax1.bar(x, df["qps"], width=x * 0.15, alpha=0.7, color="#4C72B0", label="QPS")
    ax2.plot(x, df["p99_ms"], "o-", color="#C44E52", linewidth=2, markersize=8, label="P99 Latency")
    ax2.plot(x, df["avg_ms"], "s--", color="#55A868", linewidth=2, markersize=6, label="Avg Latency")

    ax1.set_xlabel("Concurrency")
    ax1.set_ylabel("QPS", color="#4C72B0")
    ax2.set_ylabel("Latency (ms)", color="#C44E52")
    ax1.set_title(f"Scenario 10: High Concurrency Test\n({df['table'].iloc[0]}, {dataframe_user_label(df)}, LIMIT 10, {dist_fn})")
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    path = os.path.join(output_dir, "10_high_concurrency_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_recall(df, output_dir):
    """PQ recall chart: recall and speedup vs top-k."""
    if df.empty:
        return

    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    x = df["limit_k"]

    ax1.plot(x, df["avg_recall"], "o-", color="#4C72B0", linewidth=2, markersize=8, label="Recall@K")
    ax2.plot(x, df["speedup"], "s--", color="#55A868", linewidth=2, markersize=7, label="Speedup")

    ax1.set_xlabel("Top-K (LIMIT)")
    ax1.set_ylabel("Recall", color="#4C72B0")
    ax2.set_ylabel("Speedup (exact / approx)", color="#55A868")
    ax1.set_ylim(0, 1.05)
    ax1.set_title(f"Scenario 11: PQ Recall Test\n({df['table'].iloc[0]})")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower left")

    plt.tight_layout()
    path = os.path.join(output_dir, "11_recall_test.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved {path}")


# ─── Repair Report ───────────────────────────────────────────────

# Map scenario name -> plot function name (for dispatch)
_SCENARIO_PLOTTERS = {
    "scale":       "plot_scale",
    "topk":        "plot_topk",
    "filter":      "plot_filter",
    "distfn":      "plot_distance_fn",
    "concurrency": "plot_concurrency",
    "largetopk":   "plot_large_topk",
    "fullscan":    "plot_full_scan",
    "cache":       "plot_cache_effect",
    "concscale":   "plot_concurrent_scale",
    "highconc":    "plot_high_concurrency",
    "recall":      "plot_recall",
}


def repair_report(report_dir, dim_conf):
    """Repair an existing benchmark report directory.

    Fixes:
      1. JSON summary — adds missing 'dist_fn' / 'search_mode' (and 'limit' for concscale) fields
      2. CSV files   — adds missing 'dist_fn' / 'search_mode' (and 'limit' for concscale) columns
      3. PNG charts  — regenerated from patched data with correct dist_fn in titles

    Args:
        report_dir: path to the benchmark_results_* directory
        dim_conf:   DIM_CONFIG entry (determines correct dist_fn)
    """
    import glob as globmod

    dist_fn = dim_conf["dist_fn"]
    search_mode = dim_conf["search_mode"]

    print("=" * 60)
    print(f"  Repair Report: {report_dir}")
    print(f"  dist_fn = {dist_fn}")
    print("=" * 60)

    # ── 1. Find and patch JSON ──
    json_files = sorted(globmod.glob(os.path.join(report_dir, "summary_*.json")))
    for jf in json_files:
        print(f"\n[JSON] Patching {os.path.basename(jf)}")
        with open(jf) as f:
            summary = json.load(f)

        changed = False
        for scenario_name, records in summary.items():
            for rec in records:
                # Add dist_fn if missing or wrong
                if scenario_name == "distfn":
                    # Scenario 4 already has per-row 'function' field; skip dist_fn
                    continue
                if rec.get("dist_fn") != dist_fn:
                    rec["dist_fn"] = dist_fn
                    changed = True
                if rec.get("search_mode") != search_mode:
                    rec["search_mode"] = search_mode
                    changed = True
                # Add limit for concscale if missing
                if scenario_name == "concscale" and "limit" not in rec:
                    rec["limit"] = 10
                    changed = True

        if changed:
            with open(jf, "w") as f:
                json.dump(summary, f, indent=2)
            print(f"  [OK] Patched")
        else:
            print(f"  [OK] Already correct, no changes needed")

    # ── 2. Find and patch CSV ──
    csv_files = sorted(globmod.glob(os.path.join(report_dir, "*.csv")))
    for cf in csv_files:
        basename = os.path.basename(cf)
        # Infer scenario name from csv filename: <scenario>_<timestamp>.csv
        scenario_name = basename.rsplit("_", 2)[0] if basename.count("_") >= 2 else basename.rsplit("_", 1)[0]
        # cache_raw doesn't need dist_fn
        if scenario_name == "cache_raw":
            continue
        # distfn has per-row 'function', not a global dist_fn
        if scenario_name == "distfn":
            continue

        print(f"\n[CSV]  Patching {basename}")
        df = pd.read_csv(cf)
        patched = False

        if "dist_fn" not in df.columns or (df["dist_fn"] != dist_fn).any():
            df["dist_fn"] = dist_fn
            patched = True
        if "search_mode" not in df.columns or (df["search_mode"] != search_mode).any():
            df["search_mode"] = search_mode
            patched = True
        if scenario_name == "concscale" and "limit" not in df.columns:
            df["limit"] = 10
            patched = True

        if patched:
            df.to_csv(cf, index=False)
            print(f"  [OK] Patched")
        else:
            print(f"  [OK] Already correct")

    # ── 3. Regenerate PNG charts from patched data ──
    print(f"\n[PLOT] Regenerating charts...")
    setup_plot_style()

    # Re-read patched JSON to get DataFrames
    if not json_files:
        print("  [SKIP] No summary JSON found, cannot regenerate charts")
        return

    with open(json_files[-1]) as f:
        summary = json.load(f)

    for scenario_name, records in summary.items():
        if scenario_name == "cache_raw":
            continue
        df = pd.DataFrame(records)

        # Dispatch to the right plot function
        plot_fn_name = _SCENARIO_PLOTTERS.get(scenario_name)
        if plot_fn_name is None:
            print(f"  [SKIP] Unknown scenario '{scenario_name}', no plotter")
            continue

        plot_fn = globals().get(plot_fn_name)
        if plot_fn is None:
            print(f"  [SKIP] Plot function '{plot_fn_name}' not found")
            continue

        try:
            # cache scenario uses raw_df, handle specially
            if scenario_name == "cache" and "cache_raw" in summary:
                raw_df = pd.DataFrame(summary["cache_raw"])
                plot_fn(raw_df, report_dir)
            elif scenario_name in ("distfn", "cache"):
                # distfn and cache plot functions don't take dist_fn
                plot_fn(df, report_dir)
            else:
                plot_fn(df, report_dir, dist_fn)
            print(f"  [OK] {scenario_name} -> {plot_fn_name}")
        except Exception as e:
            print(f"  [FAIL] {scenario_name}: {e}")

    print(f"\nRepair complete! Results in {report_dir}/")


# ─── Main ────────────────────────────────────────────────────────

ALL_SCENARIOS = [
    "scale", "topk", "filter", "distfn", "concurrency",
    "largetopk", "fullscan", "cache", "concscale", "highconc", "recall",
]

def main():
    global DORIS_HOST, DORIS_PORT, DORIS_USER, DORIS_PASS, DORIS_DB, BENCH_RUNS, NUM_QUERIES, USER_MODE, FIXED_USER_ID

    parser = argparse.ArgumentParser(
        description="Doris Vector Search Benchmark",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--host", default=DORIS_HOST)
    parser.add_argument("--port", type=int, default=DORIS_PORT)
    parser.add_argument("--user", default=DORIS_USER)
    parser.add_argument("--password", default=DORIS_PASS)
    parser.add_argument("--db", default=DORIS_DB)
    parser.add_argument("--output", default=OUTPUT_DIR)
    parser.add_argument("--runs", type=int, default=BENCH_RUNS, help="Iterations per test case")
    parser.add_argument("--queries", type=int, default=NUM_QUERIES, help="Number of query vectors")
    parser.add_argument("--user-mode", default="fixed", choices=["fixed", "query"],
                        help="User filter mode: fixed uses one user_id for all single-user scenarios; "
                             "query uses each sampled query vector's own user_id")
    parser.add_argument("--fixed-user-id", type=int, default=FIXED_USER_ID,
                        help="Fixed user_id used when --user-mode fixed (default: 42)")
    parser.add_argument("--dim", type=int, default=128, choices=[128, 768],
                        help="Vector dimension: 128 (SIFT) or 768 (Cohere)")
    parser.add_argument("--search-mode", default="bruteforce", choices=["bruteforce", "pq_on_disk"],
                        help="Search mode: brute-force scan or pq_on_disk ANN index")
    parser.add_argument("--scenarios", nargs="*", default=None,
                        help="Run specific scenarios:\n"
                             "  scale       - Latency vs data scale\n"
                             "  topk        - Latency vs Top-K\n"
                             "  filter      - Latency vs filter selectivity\n"
                             "  distfn      - Distance function comparison\n"
                             "  concurrency - Concurrent query throughput\n"
                             "  largetopk   - Extended Top-K (100-5000)\n"
                             "  fullscan    - Full table scan (no filter)\n"
                             "  cache       - Cache warming effect\n"
                             "  concscale   - Concurrency across table sizes\n"
                             "  highconc    - High concurrency (up to 64)\n"
                             "  recall      - PQ recall vs exact search\n"
                             "  (default: run all)")
    parser.add_argument("--parallel", type=int, default=0,
                        help="Set scan/pipeline parallelism (0=auto, 1=serial)")
    parser.add_argument("--concurrency-levels", type=int, nargs="+", default=None,
                        help="Concurrency levels for concscale test (default: 1 4 8 16 32)")
    parser.add_argument("--duration", type=int, default=30,
                        help="Duration in seconds for each concscale test case (default: 30)")
    parser.add_argument("--limit", type=int, default=10,
                        help="LIMIT N for concscale queries (default: 10)")
    parser.add_argument("--tables", nargs="+", default=None, metavar="SCALE",
                        help="Table scales to test for multi-table scenarios\n"
                             "(scale, fullscan, concscale). E.g. --tables 10k 100k\n"
                             "(default: all 4 scales: 10k 100k 500k 1m)")
    parser.add_argument("--table-key", default=None, metavar="SCALE",
                        help="Table scale for single-table scenarios\n"
                             "(topk, filter, distfn, concurrency, largetopk, cache, highconc)\n"
                             "E.g. --table-key 500k  (default: 100k)")
    parser.add_argument("--repair-report", metavar="DIR",
                        help="Repair an existing report directory: fix dist_fn in JSON/CSV\n"
                             "and regenerate PNG charts. Requires --dim to specify the\n"
                             "correct distance function. No Doris connection needed.")
    args = parser.parse_args()

    # ── Repair mode: fix existing report and exit ──
    if args.repair_report:
        dim_conf = resolve_dim_conf(args.dim, args.search_mode)
        repair_report(args.repair_report, dim_conf)
        return

    DORIS_HOST = args.host
    DORIS_PORT = args.port
    DORIS_USER = args.user
    DORIS_PASS = args.password
    DORIS_DB   = args.db
    BENCH_RUNS = args.runs
    NUM_QUERIES = args.queries
    USER_MODE = args.user_mode
    FIXED_USER_ID = args.fixed_user_id

    # Apply parallelism constraints if requested
    if args.parallel > 0:
        SESSION_VARS["parallel_pipeline_task_num"] = args.parallel
        SESSION_VARS["parallel_fragment_exec_instance_num"] = args.parallel
        SESSION_VARS["max_scanners_concurrency"] = args.parallel

    full_dim_conf = resolve_dim_conf(args.dim, args.search_mode)
    dim_conf = full_dim_conf
    TABLES = dim_conf["tables"]

    # Filter tables if --tables specified
    if args.tables:
        args.tables = [t.strip().lower() for t in args.tables]
        invalid = [t for t in args.tables if t not in dim_conf["tables"]]
        if invalid:
            parser.error(f"Unknown table scale(s): {invalid}. "
                         f"Valid: {list(dim_conf['tables'].keys())}")
        dim_conf = dict(dim_conf)  # shallow copy to avoid mutating global
        dim_conf["tables"] = {k: v for k, v in dim_conf["tables"].items() if k in args.tables}
        TABLES = dim_conf["tables"]

    # Resolve table_key for single-table scenarios. If only one table scale is
    # selected via --tables, use it as the implicit single-table target.
    if args.table_key:
        table_key = args.table_key.strip().lower()
    elif args.tables and len(args.tables) == 1:
        table_key = args.tables[0]
    else:
        table_key = "100k"
    if table_key not in dim_conf["tables"]:
        # table_key not in filtered set — check if it exists in the full config
        full_tables = full_dim_conf["tables"]
        if table_key not in full_tables:
            parser.error(f"Unknown table-key '{table_key}'. "
                         f"Valid: {list(full_tables.keys())}")
        # table_key exists but was filtered out by --tables. Keep the filtered
        # table list for multi-table scenarios, but make the single-table target
        # available for topk/filter/concurrency/recall-style scenarios.
        dim_conf = dict(dim_conf)
        dim_conf["tables"] = dict(dim_conf["tables"])
        dim_conf["tables"][table_key] = full_tables[table_key]

    # Append dimension suffix to output dir if not already present
    output_dir = args.output
    if not output_dir.endswith(dim_conf["suffix"]):
        output_dir = f"{output_dir}_{dim_conf['suffix']}"

    os.makedirs(output_dir, exist_ok=True)
    setup_plot_style()

    run_all = args.scenarios is None
    scenarios = set(args.scenarios or [])

    print("=" * 60)
    print(f"  Doris Vector Search Benchmark [{dim_conf['label']}]")
    print(f"  Host: {DORIS_HOST}:{DORIS_PORT}  DB: {DORIS_DB}")
    print(f"  Dim: {args.dim}  Mode: {args.search_mode}  Dist: {dim_conf['dist_fn']}")
    print(f"  Runs: {BENCH_RUNS}  Query vectors: {NUM_QUERIES}")
    print(f"  User mode: {USER_MODE} ({benchmark_user_label()})")
    print(f"  Tables: {list(dim_conf['tables'].keys())}  Table-key: {table_key}")
    print(f"  Parallelism: {args.parallel if args.parallel > 0 else 'auto'}")
    print(f"  Output: {output_dir}/")
    if not run_all:
        print(f"  Scenarios: {', '.join(sorted(scenarios))}")
    else:
        print(f"  Scenarios: ALL ({len(ALL_SCENARIOS)} tests)")
    print("=" * 60)

    # Load query vectors
    query_vecs = load_query_vectors(dim_conf, n=NUM_QUERIES)

    conn = get_conn()
    all_results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dist_fn = dim_conf["dist_fn"]

    # Scenario 1: Scale test
    if run_all or "scale" in scenarios:
        df = test_scale(conn, query_vecs, dim_conf)
        all_results["scale"] = df
        plot_scale(df, output_dir, dist_fn)

    # Scenario 2: Top-K test
    if run_all or "topk" in scenarios:
        df = test_topk(conn, query_vecs, dim_conf, table_key=table_key)
        all_results["topk"] = df
        plot_topk(df, output_dir, dist_fn)

    # Scenario 3: Filter selectivity
    if run_all or "filter" in scenarios:
        df = test_filter(conn, query_vecs, dim_conf, table_key=table_key)
        all_results["filter"] = df
        plot_filter(df, output_dir, dist_fn)

    # Scenario 4: Distance function comparison
    if run_all or "distfn" in scenarios:
        df = test_distance_fn(conn, query_vecs, dim_conf, table_key=table_key)
        all_results["distfn"] = df
        plot_distance_fn(df, output_dir)

    # Scenario 6: Large Top-K test
    if run_all or "largetopk" in scenarios:
        df = test_large_topk(conn, query_vecs, dim_conf, table_key=table_key)
        all_results["largetopk"] = df
        plot_large_topk(df, output_dir, dist_fn)

    # Scenario 7: Full scan test
    if run_all or "fullscan" in scenarios:
        df = test_full_scan(conn, query_vecs, dim_conf)
        all_results["fullscan"] = df
        plot_full_scan(df, output_dir, dist_fn)

    # Scenario 8: Cache effect test
    if run_all or "cache" in scenarios:
        summary_df, raw_df = test_cache_effect(conn, query_vecs, dim_conf, table_key=table_key)
        all_results["cache"] = summary_df
        all_results["cache_raw"] = raw_df
        plot_cache_effect(raw_df, output_dir)

    conn.close()

    # Scenario 5: Concurrency (uses its own connections)
    if run_all or "concurrency" in scenarios:
        df = test_concurrency(query_vecs, dim_conf, table_key=table_key)
        all_results["concurrency"] = df
        plot_concurrency(df, output_dir, dist_fn)

    # Scenario 9: Concurrent scale test
    if run_all or "concscale" in scenarios:
        df = test_concurrent_scale(query_vecs, dim_conf,
                                   concurrency_levels=args.concurrency_levels,
                                   duration=args.duration,
                                   limit=args.limit)
        all_results["concscale"] = df
        plot_concurrent_scale(df, output_dir, dist_fn)

    # Scenario 10: High concurrency test
    if run_all or "highconc" in scenarios:
        df = test_high_concurrency(query_vecs, dim_conf, table_key=table_key)
        all_results["highconc"] = df
        plot_high_concurrency(df, output_dir, dist_fn)

    if (run_all or "recall" in scenarios) and args.search_mode == "pq_on_disk":
        df = test_recall(query_vecs, dim_conf, table_key=table_key)
        all_results["recall"] = df
        plot_recall(df, output_dir)

    # Save all results to CSV
    print(f"\n{'=' * 60}")
    print("Saving results...")
    print(f"{'=' * 60}")
    for name, df in all_results.items():
        csv_path = os.path.join(output_dir, f"{name}_{timestamp}.csv")
        df.to_csv(csv_path, index=False)
        print(f"  {csv_path}")

    # Save combined summary (exclude cache_raw from JSON for brevity)
    summary_path = os.path.join(output_dir, f"summary_{timestamp}.json")
    summary = {}
    for name, df in all_results.items():
        if name == "cache_raw":
            continue
        summary[name] = df.to_dict(orient="records")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  {summary_path}")

    print(f"\nBenchmark complete! Results in {output_dir}/")


if __name__ == "__main__":
    main()
