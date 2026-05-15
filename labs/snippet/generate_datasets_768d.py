#!/usr/bin/env python3
"""
Generate the base 768D vector embedding dataset from Cohere 1M source data.

Source: Cohere/wikipedia-22-12 768D float vectors (1M rows from VectorDBBench)

Only generates the smallest dataset (dataset_768d_1w: 100 users x 10,000 vectors).
Larger tables (10w/50w/100w) are built inside Doris via INSERT INTO SELECT ETL
(see load_all.sh).

Output format: TSV (tab-separated), gzip compressed, sharded by ~1M rows.
Columns: user_id<TAB>id<TAB>[v1,v2,...,v768]

Usage:
  python3 generate_datasets_768d.py                    # generate base dataset (auto-downloads source if missing)
"""

import gzip
import os
import sys
import time
import tempfile
import numpy as np
from multiprocessing import Pool
import pyarrow.parquet as pq
import pyarrow as pa

# Configuration
SOURCE_FILE = "datasets/source_768d/cohere_1m_train.parquet"

# Download sources (tried in order):
#   1. Aliyun OSS (VectorDBBench mirror, China-friendly, single file)
#   2. AWS S3 / CloudFront (VectorDBBench official, single file)
#   3. HuggingFace (4 shards, need merge)
DOWNLOAD_SOURCES = [
    {
        "label":  "Aliyun OSS (China)",
        "url":    "https://assets.zilliz.com.cn/benchmark/cohere_medium_1m/train.parquet",
        "single": True,
    },
    {
        "label":  "AWS S3 (Global)",
        "url":    "https://assets.zilliz.com/benchmark/cohere_medium_1m/train.parquet",
        "single": True,
    },
    {
        "label":  "HuggingFace (4 shards)",
        "urls": [
            "https://huggingface.co/datasets/Cohere/wikipedia-22-12-simple-embeddings/resolve/main/data/train-00000-of-00004-1a1932c9ca1c7152.parquet",
            "https://huggingface.co/datasets/Cohere/wikipedia-22-12-simple-embeddings/resolve/main/data/train-00001-of-00004-f4a4f5540ade14b4.parquet",
            "https://huggingface.co/datasets/Cohere/wikipedia-22-12-simple-embeddings/resolve/main/data/train-00002-of-00004-ff770df3ab420d14.parquet",
            "https://huggingface.co/datasets/Cohere/wikipedia-22-12-simple-embeddings/resolve/main/data/train-00003-of-00004-85b3dbbc960e92ec.parquet",
        ],
        "single": False,
    },
]
OUTPUT_BASE = "datasets"
NUM_USERS = 100
SHARD_SIZE = 1_000_000   # rows per shard
SEED = 42
WRITE_CHUNK = 20_000     # lines to batch before writing
NUM_WORKERS = 32
COMPRESS_LEVEL = 1        # fast gzip
FLOAT_FMT = "%.6g"       # 6 significant digits (float32 has ~7)

DATASETS = [
    ("dataset_768d_1w",   10_000),
    # Larger datasets (10w/50w/100w) are built via Doris ETL in load_all.sh
]

# ─── Phase 0: Download source data if missing ────────────────────

def _download_file(url, dest, timeout=60):
    """Try to download a file, return True on success."""
    ret = os.system(
        f'curl -L --fail --retry 3 --retry-delay 5 '
        f'--connect-timeout {timeout} -o "{dest}" "{url}"'
    )
    return ret == 0


def ensure_source_data(filepath):
    """Download Cohere 768D source parquet if missing.

    Tries multiple sources in order:
      1. Aliyun OSS  (China-friendly, single file, ~3GB)
      2. AWS S3      (Global CDN, single file, ~3GB)
      3. HuggingFace (4 shards, merge needed)
    """
    if os.path.exists(filepath):
        print(f"Source file already exists: {filepath}")
        return

    source_dir = os.path.dirname(filepath)
    os.makedirs(source_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="cohere_dl_", dir=source_dir)

    try:
        for src in DOWNLOAD_SOURCES:
            label = src["label"]
            print(f"\nTrying source: {label} ...")

            try:
                if src["single"]:
                    # Single file download
                    tmp_file = os.path.join(tmp_dir, "train.parquet")
                    if _download_file(src["url"], tmp_file):
                        os.rename(tmp_file, filepath)
                        print(f"  Done: {filepath}")
                        return
                    print(f"  Failed.")
                else:
                    # Multi-shard download + merge
                    parts = []
                    ok = True
                    for i, url in enumerate(src["urls"]):
                        fname = os.path.basename(url)
                        dest = os.path.join(tmp_dir, fname)
                        print(f"  [{i+1}/{len(src['urls'])}] {fname} ...")
                        if not _download_file(url, dest):
                            ok = False
                            break
                        parts.append(dest)
                    if ok:
                        print("  Merging parquet files (emb column only)...")
                        tables = [pq.read_table(p, columns=["emb"]) for p in parts]
                        merged = pa.concat_tables(tables)
                        pq.write_table(merged, filepath)
                        print(f"  Done: {merged.num_rows:,} rows -> {filepath}")
                        return
                    print(f"  Failed.")
            except Exception as e:
                print(f"  Error: {e}")

        raise RuntimeError(
            f"Failed to download source data from all sources.\n"
            f"  Please manually place the file at: {filepath}"
        )

    except Exception:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── Phase 1: Load and pre-format source vectors ──────────────────
# Globals inherited by fork (copy-on-write)
EMBEDDINGS = []     # list of pre-formatted vector strings


def _format_chunk(chunk_arr):
    """Format a chunk of numpy vectors into string list. Used by parallel pre-format."""
    result = []
    for vec in chunk_arr:
        result.append("[" + ",".join(FLOAT_FMT % v for v in vec) + "]")
    return result


def load_and_preformat(filepath):
    """Load parquet → numpy array → pre-format all vectors as strings in parallel."""
    print(f"Phase 1: Loading source data from {filepath}...")
    t0 = time.time()

    pf = pq.ParquetFile(filepath)
    num_rows = pf.metadata.num_rows
    print(f"  Parquet: {num_rows:,} rows, {pf.metadata.num_row_groups} row groups")

    # Read all vectors into numpy
    all_vecs = []
    loaded = 0
    for batch in pf.iter_batches(batch_size=50_000, columns=["emb"]):
        emb_list = batch.column("emb").to_pylist()
        all_vecs.append(np.array(emb_list, dtype=np.float32))
        loaded += len(emb_list)
        print(f"  Reading parquet: {loaded:,}/{num_rows:,}...", end="\r", flush=True)

    arr = np.vstack(all_vecs)
    del all_vecs
    t1 = time.time()
    print(f"  Loaded {arr.shape[0]:,} x {arr.shape[1]}D in {t1 - t0:.1f}s "
          f"({arr.nbytes / 1e9:.2f} GB)     ")

    # Pre-format in parallel: split array into chunks for workers
    print(f"  Pre-formatting {arr.shape[0]:,} vector strings ({NUM_WORKERS} workers)...")
    chunk_size = max(1, arr.shape[0] // NUM_WORKERS)
    chunks = [arr[i:i + chunk_size] for i in range(0, arr.shape[0], chunk_size)]

    embeddings = []
    with Pool(processes=min(NUM_WORKERS, len(chunks))) as pool:
        for chunk_result in pool.imap(_format_chunk, chunks):
            embeddings.extend(chunk_result)
            print(f"  Formatted: {len(embeddings):,}/{num_rows:,}...", end="\r", flush=True)

    del arr  # free numpy array
    t2 = time.time()

    avg_len = sum(len(s) for s in embeddings[:1000]) / 1000
    mem_mb = len(embeddings) * avg_len / (1024 * 1024)
    print(f"  Pre-formatted {len(embeddings):,} vectors in {t2 - t1:.1f}s "
          f"(avg {avg_len:.0f} chars, ~{mem_mb:.0f} MB strings)   ")
    print(f"  Total Phase 1: {t2 - t0:.1f}s")
    return embeddings


# ─── Phase 2: Generate datasets (string lookup only) ─────────────

def generate_shard(args):
    """Worker function: generate one shard file.
    Uses fork-inherited EMBEDDINGS list (string lookups only, no formatting).
    """
    shard_idx, user_ids, vectors_per_user, output_dir, base_seed = args
    source_size = len(EMBEDDINGS)
    shard_path = os.path.join(output_dir, f"shard_{shard_idx:03d}.tsv.gz")
    total_written = 0

    with gzip.open(shard_path, "wb", compresslevel=COMPRESS_LEVEL) as fout:
        for user_id in user_ids:
            rng = np.random.default_rng(base_seed + user_id)
            indices = rng.integers(0, source_size, size=vectors_per_user)

            for chunk_start in range(0, vectors_per_user, WRITE_CHUNK):
                chunk_end = min(chunk_start + WRITE_CHUNK, vectors_per_user)
                chunk_indices = indices[chunk_start:chunk_end]

                lines = []
                for i, idx in enumerate(chunk_indices, start=chunk_start):
                    lines.append(f"{user_id}\t{i}\t{EMBEDDINGS[idx]}")
                chunk_bytes = ("\n".join(lines) + "\n").encode("utf-8")
                fout.write(chunk_bytes)
                total_written += len(chunk_indices)

    file_size = os.path.getsize(shard_path)
    return shard_idx, total_written, file_size


def generate_dataset(dataset_name, vectors_per_user):
    """Generate a dataset using multiprocessing across shards."""
    total_rows = NUM_USERS * vectors_per_user
    output_dir = os.path.join(OUTPUT_BASE, dataset_name)
    os.makedirs(output_dir, exist_ok=True)

    users_per_shard = max(1, SHARD_SIZE // vectors_per_user)
    shard_tasks = []
    shard_idx = 0
    for start_user in range(0, NUM_USERS, users_per_shard):
        end_user = min(start_user + users_per_shard, NUM_USERS)
        user_ids = list(range(start_user, end_user))
        shard_tasks.append((shard_idx, user_ids, vectors_per_user, output_dir, SEED))
        shard_idx += 1

    num_shards = len(shard_tasks)
    workers = min(NUM_WORKERS, num_shards)

    print(f"\n{'=' * 60}")
    print(f"Phase 2: {dataset_name} ({NUM_USERS} users x {vectors_per_user:,} = {total_rows:,} rows)")
    print(f"  Shards: {num_shards} ({users_per_shard} users/shard)")
    print(f"  Workers: {workers}")
    print(f"  Output: {output_dir}/")
    print(f"{'=' * 60}")

    t0 = time.time()
    total_written = 0
    total_size = 0

    with Pool(processes=workers) as pool:
        for result in pool.imap_unordered(generate_shard, shard_tasks):
            s_idx, s_rows, s_size = result
            total_written += s_rows
            total_size += s_size
            elapsed = time.time() - t0
            pct = total_written / total_rows * 100
            speed = total_written / elapsed if elapsed > 0 else 0
            print(f"  Shard {s_idx:03d} done | "
                  f"{total_written:>12,}/{total_rows:,} ({pct:5.1f}%) | "
                  f"{elapsed:7.1f}s | {speed:,.0f} rows/s")

    elapsed = time.time() - t0
    print(f"\n  Done! {total_written:,} rows in {elapsed:.1f}s "
          f"({total_written / elapsed:,.0f} rows/s)")
    print(f"  Compressed size: {total_size / (1024 ** 3):.2f} GB ({num_shards} shards)")
    return total_written


def main():
    global EMBEDDINGS

    ensure_source_data(SOURCE_FILE)
    EMBEDDINGS = load_and_preformat(SOURCE_FILE)

    t0 = time.time()
    for dataset_name, vectors_per_user in DATASETS:
        generate_dataset(dataset_name, vectors_per_user)

    elapsed = time.time() - t0
    print(f"\nAll done! Total generation time: {elapsed:.0f}s")
    print(f"Next step: run load_all.sh to import into Doris and ETL-expand larger tables.")


if __name__ == "__main__":
    main()
